"""
CLI Entrypoint for FERPA Feedback Pipeline

Provides command-line interface for processing teacher comment documents
with FERPA-compliant PII detection and anonymization.

Usage:
    ferpa-feedback process INPUT_PATH [OPTIONS]
    ferpa-feedback warmup
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ferpa_feedback.models import TeacherDocument
from ferpa_feedback.pipeline import create_pipeline


def generate_anonymized_report(document: TeacherDocument, input_path: Path, output_dir: Path) -> Path:
    """
    Generate a document showing anonymized text for each comment.

    Args:
        document: The processed TeacherDocument with anonymized text
        input_path: Path to the original input file
        output_dir: Directory to save the output

    Returns:
        Path to the generated report file
    """
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create report filename
    report_name = f"{input_path.stem}_anonymized.txt"
    report_path = output_dir / report_name

    lines = []
    lines.append("=" * 70)
    lines.append("ANONYMIZED COMMENTS")
    lines.append("=" * 70)
    lines.append(f"Original Document: {input_path.name}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Total Comments: {len(document.comments)}")

    # Count PII replacements
    total_pii = sum(len(c.anonymization_mappings) for c in document.comments)
    lines.append(f"Total PII Instances Replaced: {total_pii}")
    lines.append("=" * 70)
    lines.append("")
    lines.append("NOTE: All personally identifiable information (PII) has been replaced")
    lines.append("with placeholder tokens like [PERSON_1], [DATE_TIME_2], etc.")
    lines.append("")

    for comment in document.comments:
        lines.append("-" * 70)
        lines.append(f"STUDENT: {comment.student_name}")
        lines.append(f"GRADE: {comment.grade}")
        lines.append(f"PII Replaced: {len(comment.anonymization_mappings)}")
        lines.append("-" * 70)
        lines.append("")

        if comment.anonymized_text:
            lines.append("ANONYMIZED TEXT:")
            lines.append(comment.anonymized_text)
        else:
            lines.append("ANONYMIZED TEXT: [No anonymization performed]")
            lines.append("")
            lines.append("ORIGINAL TEXT:")
            lines.append(comment.comment_text)

        lines.append("")

        # Show what was replaced
        if comment.anonymization_mappings:
            lines.append("REPLACEMENTS MADE:")
            for mapping in comment.anonymization_mappings:
                lines.append(f"  - {mapping.entity_type}: \"{mapping.original}\" → \"{mapping.placeholder}\"")
            lines.append("")

        lines.append("")

    lines.append("=" * 70)
    lines.append("END OF ANONYMIZED DOCUMENT")
    lines.append("=" * 70)

    # Write report
    report_path.write_text("\n".join(lines), encoding="utf-8")

    return report_path


def generate_grammar_report(document: TeacherDocument, input_path: Path) -> Path:
    """
    Generate a grammar report document showing all errors found.

    Args:
        document: The processed TeacherDocument with grammar issues
        input_path: Path to the original input file

    Returns:
        Path to the generated report file
    """
    # Create report filename in same directory as input
    report_name = f"{input_path.stem}_grammar_report.txt"
    report_path = input_path.parent / report_name

    lines = []
    lines.append("=" * 70)
    lines.append("GRAMMAR CHECK REPORT")
    lines.append("=" * 70)
    lines.append(f"Document: {input_path.name}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Total Comments: {len(document.comments)}")

    # Count totals
    total_issues = sum(len(c.grammar_issues) for c in document.comments)
    comments_with_issues = sum(1 for c in document.comments if c.grammar_issues)

    lines.append(f"Comments with Issues: {comments_with_issues}")
    lines.append(f"Total Issues Found: {total_issues}")
    lines.append("=" * 70)
    lines.append("")

    # Group by student
    for comment in document.comments:
        if not comment.grammar_issues:
            continue

        lines.append("-" * 70)
        lines.append(f"STUDENT: {comment.student_name}")
        lines.append(f"GRADE: {comment.grade}")
        lines.append(f"Issues Found: {len(comment.grammar_issues)}")
        lines.append("-" * 70)
        lines.append("")
        lines.append("COMMENT TEXT:")
        lines.append(comment.comment_text)
        lines.append("")
        lines.append("ISSUES:")
        lines.append("")

        for i, issue in enumerate(comment.grammar_issues, 1):
            # Extract the problematic text from the comment
            error_text = comment.comment_text[issue.offset:issue.offset + issue.length]

            lines.append(f"  {i}. {issue.message}")
            lines.append(f"     Error: \"{error_text}\"")
            lines.append(f"     Location: character {issue.offset}-{issue.offset + issue.length}")
            lines.append(f"     Rule: {issue.rule_id}")
            lines.append(f"     Confidence: {issue.confidence:.0%}")

            if issue.suggestions:
                suggestions_str = ", ".join(f'"{s}"' for s in issue.suggestions[:3])
                lines.append(f"     Suggestions: {suggestions_str}")

            lines.append("")

        lines.append("")

    # Summary by rule type
    lines.append("=" * 70)
    lines.append("SUMMARY BY ERROR TYPE")
    lines.append("=" * 70)

    rule_counts: dict[str, int] = {}
    for comment in document.comments:
        for issue in comment.grammar_issues:
            rule_counts[issue.rule_id] = rule_counts.get(issue.rule_id, 0) + 1

    for rule_id, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {rule_id}: {count}")

    lines.append("")
    lines.append("=" * 70)
    lines.append("END OF REPORT")
    lines.append("=" * 70)

    # Write report
    report_path.write_text("\n".join(lines), encoding="utf-8")

    return report_path

app = typer.Typer(
    name="ferpa-feedback",
    help="FERPA-compliant teacher comment feedback system",
    add_completion=False,
)

console = Console()


@app.command()
def process(
    input_path: Path = typer.Argument(
        ...,
        help="Path to .docx file or directory containing documents",
        exists=True,
    ),
    roster: Optional[Path] = typer.Option(
        None,
        "--roster",
        "-r",
        help="Path to roster CSV file for name matching",
        exists=True,
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to settings.yaml configuration file",
        exists=True,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path for processed results",
    ),
    stages: str = typer.Option(
        "0,1,2,3",
        "--stages",
        "-s",
        help="Comma-separated list of stages to run (0=ingestion, 1=grammar, 2=names, 3=anonymize)",
    ),
) -> None:
    """
    Process teacher comment documents through the FERPA pipeline.

    Runs documents through grammar checking, name verification, and
    anonymization stages. All processing is local until explicitly
    sent to external APIs.
    """
    console.print(f"[bold blue]Processing:[/] {input_path}")

    # Parse stages
    stage_list = [int(s.strip()) for s in stages.split(",")]
    console.print(f"[dim]Stages: {stage_list}[/]")

    # Create pipeline
    config_path = str(config) if config else None
    roster_path = str(roster) if roster else None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Initializing pipeline...", total=None)
        pipeline = create_pipeline(config_path=config_path, roster_path=roster_path)

    # Collect files to process
    if input_path.is_dir():
        files = list(input_path.glob("**/*.docx"))
        console.print(f"[bold]Found {len(files)} documents[/]")
    else:
        files = [input_path]

    if not files:
        console.print("[yellow]No documents found to process[/]")
        raise typer.Exit(code=1)

    # Process documents
    processed_docs: list[tuple[Path, TeacherDocument]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing documents...", total=len(files))

        for file_path in files:
            progress.update(task, description=f"Processing: {file_path.name}")
            try:
                document = pipeline.process_document(file_path)
                processed_docs.append((file_path, document))
                console.print(
                    f"  [green]Processed:[/] {file_path.name} "
                    f"({len(document.comments)} comments)"
                )
            except Exception as e:
                console.print(f"  [red]Failed:[/] {file_path.name} - {e}")
            progress.advance(task)

    console.print("\n[bold green]Processing complete![/]")

    # Generate reports for each processed document
    # Determine output directory (relative to input or current working directory)
    output_dir = input_path / "outputs" if input_path.is_dir() else input_path.parent / "outputs"

    for file_path, document in processed_docs:
        # Grammar report (in same folder as input)
        total_issues = sum(len(c.grammar_issues) for c in document.comments)
        if total_issues > 0:
            report_path = generate_grammar_report(document, file_path)
            console.print(
                f"[blue]Grammar report:[/] {report_path.name} "
                f"({total_issues} issues found)"
            )
        else:
            console.print(f"[dim]No grammar issues found in {file_path.name}[/]")

        # Anonymized output (in outputs folder)
        total_pii = sum(len(c.anonymization_mappings) for c in document.comments)
        if total_pii > 0:
            anon_path = generate_anonymized_report(document, file_path, output_dir)
            console.print(
                f"[green]Anonymized output:[/] {anon_path} "
                f"({total_pii} PII instances replaced)"
            )
        else:
            console.print(f"[dim]No PII found to anonymize in {file_path.name}[/]")


@app.command()
def warmup() -> None:
    """
    Pre-load LanguageTool server to reduce cold start latency.

    This command initializes the LanguageTool Java server before
    processing begins, avoiding the 10-30 second cold start delay.
    """
    from ferpa_feedback.stage_1_grammar import GrammarChecker

    console.print("[bold blue]Warming up LanguageTool...[/]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Initializing LanguageTool server...", total=None)

        try:
            # Create GrammarChecker and force lazy load of LanguageTool
            checker = GrammarChecker()
            progress.update(task, description="Starting LanguageTool Java server...")

            # Force the lazy initialization by accessing the tool property
            _ = checker.tool

            progress.update(task, description="LanguageTool server started")

            # Run a simple check to verify the server is responsive
            progress.update(task, description="Verifying server is responsive...")
            _ = checker.check_text("Test sentence.")

        except Exception as e:
            console.print(f"[red]Failed to warm up LanguageTool: {e}[/]")
            raise typer.Exit(code=1) from e

    console.print("[bold green]LanguageTool ready.[/]")


@app.command()
def review(
    port: int = typer.Option(8000, "--port", "-p", help="Port to run the review server on"),
) -> None:
    """
    Start the review UI server.

    Launches a FastAPI-based web interface for human review of processed
    comments. Requires optional dependencies: pip install ferpa-feedback[review-ui]
    """
    try:
        import uvicorn

        from ferpa_feedback.stage_5_review import ReviewQueue, create_review_app

        console.print(f"[bold blue]Starting review server on port {port}...[/]")
        queue = ReviewQueue()
        review_app = create_review_app(queue)
        uvicorn.run(review_app, host="0.0.0.0", port=port)
    except ImportError as e:
        console.print("[red]Review UI requires optional dependencies.[/]")
        console.print("[yellow]Install with: pip install ferpa-feedback[review-ui][/]")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
