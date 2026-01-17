"""
CLI Entrypoint for FERPA Feedback Pipeline

Provides command-line interface for processing teacher comment documents
with FERPA-compliant PII detection and anonymization.

Usage:
    ferpa-feedback process INPUT_PATH [OPTIONS]
    ferpa-feedback gdrive-process ROOT_FOLDER [OPTIONS]
    ferpa-feedback warmup
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table
from rich.tree import Tree

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


@app.command("gdrive-process")
def gdrive_process(
    root_folder: str = typer.Argument(
        ...,
        help="Google Drive folder ID to process (the long string from the folder URL)",
    ),
    target_folder: Optional[List[str]] = typer.Option(
        None,
        "--target-folder",
        "-t",
        help="Filter to specific folder names (supports glob patterns like 'September*'). Can be repeated.",
    ),
    list_folders: bool = typer.Option(
        False,
        "--list-folders",
        "-l",
        help="List folder structure without processing",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be processed without actually processing",
    ),
    output_local: Optional[Path] = typer.Option(
        None,
        "--output-local",
        "-o",
        help="Write results to local directory instead of uploading to Drive",
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
    parallel: int = typer.Option(
        5,
        "--parallel",
        "-p",
        help="Number of parallel downloads (default: 5)",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Interactively select folders to process",
    ),
) -> None:
    """
    Process documents from Google Drive through the FERPA pipeline.

    Downloads documents from a shared Google Drive folder, processes them
    through grammar checking, name verification, and anonymization stages,
    then uploads results back to Drive (or saves locally with --output-local).

    First run requires OAuth2 authentication - a browser window will open
    for authorization.

    Examples:
        # List folder structure
        ferpa-feedback gdrive-process 1abc123xyz --list-folders

        # Process all documents
        ferpa-feedback gdrive-process 1abc123xyz

        # Process only September folders
        ferpa-feedback gdrive-process 1abc123xyz -t "September*"

        # Process Interim 1 and Interim 3
        ferpa-feedback gdrive-process 1abc123xyz -t "Interim 1*" -t "Interim 3*"

        # Dry run to see what would be processed
        ferpa-feedback gdrive-process 1abc123xyz --dry-run

        # Save results locally instead of uploading to Drive
        ferpa-feedback gdrive-process 1abc123xyz -o ./output
    """
    # Import gdrive components (deferred to avoid loading at CLI startup)
    try:
        from ferpa_feedback.gdrive.auth import OAuth2Authenticator
        from ferpa_feedback.gdrive.config import DriveConfig
        from ferpa_feedback.gdrive.processor import DriveProcessor, ProcessingProgress
    except ImportError as e:
        console.print("[red]Google Drive dependencies not installed.[/]")
        console.print("[yellow]Install with: pip install google-api-python-client google-auth-oauthlib[/]")
        raise typer.Exit(1) from e

    console.print(f"[bold blue]Google Drive Processing:[/] {root_folder}")

    # Initialize configuration
    drive_config = DriveConfig()
    if parallel:
        drive_config.processing.max_concurrent_downloads = parallel

    # Initialize authenticator
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Authenticating with Google Drive...", total=None)
        try:
            authenticator = OAuth2Authenticator(
                client_secrets_path=drive_config.auth.oauth2.client_secrets_path,
                token_path=drive_config.auth.oauth2.token_path,
            )
            _ = authenticator.get_service()
            console.print(f"[green]Authenticated as:[/] {authenticator.service_account_email}")
        except Exception as e:
            console.print(f"[red]Authentication failed:[/] {e}")
            console.print("\n[yellow]Make sure you have client_secrets.json in the current directory.[/]")
            console.print("[yellow]Download from Google Cloud Console > APIs & Services > Credentials[/]")
            raise typer.Exit(1) from e

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

    # Create processor
    processor = DriveProcessor(
        authenticator=authenticator,
        pipeline=pipeline,
        config=drive_config,
    )

    # Handle --list-folders option
    if list_folders:
        console.print("\n[bold]Discovering folder structure...[/]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Scanning folders...", total=None)
            try:
                folder_map = processor.list_folders(root_folder)
            except Exception as e:
                console.print(f"[red]Failed to access folder:[/] {e}")
                console.print(f"\n[yellow]Make sure the folder is shared with {authenticator.service_account_email}[/]")
                raise typer.Exit(1) from e

        # Print folder tree
        console.print("\n[bold]Folder Structure:[/]")
        _print_folder_tree(folder_map.root, console)

        console.print("\n[bold]Summary:[/]")
        console.print(f"  Total folders: {folder_map.total_folders}")
        console.print(f"  Total documents: {folder_map.total_documents}")
        console.print(f"  Leaf folders (processing targets): {len(folder_map.get_leaf_folders())}")
        raise typer.Exit(0)

    # Handle --interactive option
    target_patterns: Optional[List[str]] = None
    if interactive:
        selected_patterns = _interactive_folder_selection(processor, root_folder, authenticator, console)
        if not selected_patterns:
            console.print("[yellow]No folders selected. Exiting.[/]")
            raise typer.Exit(0)
        target_patterns = selected_patterns
    else:
        # Process documents
        target_patterns = list(target_folder) if target_folder else None

    if target_patterns:
        console.print(f"[dim]Target patterns: {', '.join(target_patterns)}[/]")

    if dry_run:
        console.print("[yellow]Dry run mode - no documents will be processed[/]")

    if output_local:
        console.print(f"[dim]Output directory: {output_local}[/]")

    # Progress callback for rich display
    def progress_callback(prog: ProcessingProgress) -> None:
        # Progress is tracked by the rich Progress context manager
        pass

    console.print("\n[bold]Processing...[/]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Starting...", total=None)

        def update_progress(prog: ProcessingProgress) -> None:
            desc = f"Processing: {prog.current_document or 'initializing'} ({prog.processed_documents}/{prog.total_documents})"
            progress.update(task, description=desc)

        try:
            summary = processor.process(
                root_folder_id=root_folder,
                target_patterns=target_patterns,
                dry_run=dry_run,
                output_local=output_local,
                progress_callback=update_progress,
            )
        except Exception as e:
            console.print(f"[red]Processing failed:[/] {e}")
            raise typer.Exit(1) from e

    # Print summary
    console.print("\n[bold green]Processing complete![/]")
    console.print("\n[bold]Summary:[/]")
    console.print(f"  Duration: {summary.duration_seconds:.1f}s")
    console.print(f"  Documents processed: {summary.successful}/{summary.total_documents}")
    console.print(f"  Failed: {summary.failed}")
    console.print(f"  Grammar issues found: {summary.grammar_issues_found}")
    console.print(f"  PII instances replaced: {summary.pii_instances_replaced}")
    console.print(f"  Uploads completed: {summary.uploads_completed}")

    if summary.errors:
        console.print(f"\n[yellow]Errors ({len(summary.errors)}):[/]")
        for error in summary.errors[:5]:  # Show first 5 errors
            console.print(f"  - {error['document']}: {error['error']}")
        if len(summary.errors) > 5:
            console.print(f"  ... and {len(summary.errors) - 5} more")

    # Return appropriate exit code
    if summary.failed > 0 and summary.successful == 0:
        raise typer.Exit(1)
    elif summary.failed > 0:
        raise typer.Exit(2)  # Partial success


def _interactive_folder_selection(
    processor: Any,
    root_folder: str,
    authenticator: Any,
    console: Console,
) -> Optional[List[str]]:
    """Interactively select folders to process.

    Displays a numbered list of unique folder names and allows the user
    to select which folders to process by number or name.

    Args:
        processor: DriveProcessor instance.
        root_folder: Root folder ID to scan.
        authenticator: Authenticated Drive authenticator.
        console: Rich console for output.

    Returns:
        List of selected folder name patterns, or None if cancelled.
    """
    # Discover folder structure
    console.print("\n[bold]Discovering folder structure...[/]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Scanning folders...", total=None)
        try:
            folder_map = processor.list_folders(root_folder)
        except Exception as e:
            console.print(f"[red]Failed to access folder:[/] {e}")
            console.print(f"\n[yellow]Make sure the folder is shared with {authenticator.service_account_email}[/]")
            return None

    # Get leaf folders (processing targets)
    leaf_folders = folder_map.get_leaf_folders()
    if not leaf_folders:
        console.print("[yellow]No leaf folders found to process.[/]")
        return None

    # Extract unique folder names at leaf level
    unique_names: dict[str, int] = {}
    for folder in leaf_folders:
        name = folder.name
        unique_names[name] = unique_names.get(name, 0) + 1

    # Sort names for consistent display
    sorted_names = sorted(unique_names.keys())

    # Display folder options in a table
    console.print("\n[bold]Available folders to process:[/]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=4)
    table.add_column("Folder Name")
    table.add_column("Count", justify="right")

    for idx, name in enumerate(sorted_names, 1):
        count = unique_names[name]
        count_str = f"{count} folder{'s' if count > 1 else ''}"
        table.add_row(str(idx), name, count_str)

    console.print(table)
    console.print()

    # Prompt for selection
    console.print("[dim]Enter folder numbers (comma-separated), names, or patterns (e.g., '1,3' or 'September*')[/]")
    console.print("[dim]Press Enter with no input to process all folders, or 'q' to quit[/]")

    selection = Prompt.ask("Select folders", default="")

    if selection.lower() == "q":
        return None

    if not selection.strip():
        # Empty input = process all
        console.print("[green]Processing all leaf folders[/]")
        return None  # None means no filter, process all

    # Parse selection
    selected_patterns: List[str] = []
    parts = [p.strip() for p in selection.split(",")]

    for part in parts:
        if not part:
            continue

        # Check if it's a number
        try:
            num = int(part)
            if 1 <= num <= len(sorted_names):
                selected_patterns.append(sorted_names[num - 1])
            else:
                console.print(f"[yellow]Invalid number: {num} (must be 1-{len(sorted_names)})[/]")
        except ValueError:
            # Not a number, treat as name or pattern
            selected_patterns.append(part)

    if selected_patterns:
        console.print(f"[green]Selected: {', '.join(selected_patterns)}[/]")

    return selected_patterns if selected_patterns else None


def _print_folder_tree(node: Any, console: Console, prefix: str = "") -> None:
    """Print folder tree using rich Tree component.

    Args:
        node: Root folder node to print (FolderNode from gdrive.discovery).
        console: Rich console for output.
        prefix: Prefix for tree branches (internal use).
    """
    tree = Tree(f"[bold]{node.name}[/] ({len(node.documents)} docs)")

    def add_children(parent_tree: Tree, folder: Any) -> None:
        for child in folder.children:
            doc_count = len(child.documents)
            is_leaf = child.is_leaf
            if is_leaf:
                branch = parent_tree.add(f"[green]{child.name}[/] ({doc_count} docs) [dim][leaf][/]")
            else:
                branch = parent_tree.add(f"{child.name} ({doc_count} docs)")
            add_children(branch, child)

    add_children(tree, node)
    console.print(tree)


if __name__ == "__main__":
    app()
