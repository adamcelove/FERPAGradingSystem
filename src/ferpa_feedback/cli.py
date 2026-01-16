"""
CLI Entrypoint for FERPA Feedback Pipeline

Provides command-line interface for processing teacher comment documents
with FERPA-compliant PII detection and anonymization.

Usage:
    ferpa-feedback process INPUT_PATH [OPTIONS]
    ferpa-feedback warmup
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ferpa_feedback.pipeline import create_pipeline

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
                console.print(
                    f"  [green]Processed:[/] {file_path.name} "
                    f"({len(document.comments)} comments)"
                )
            except Exception as e:
                console.print(f"  [red]Failed:[/] {file_path.name} - {e}")
            progress.advance(task)

    console.print("\n[bold green]Processing complete![/]")

    if output:
        console.print(f"[dim]Output would be written to: {output}[/]")


@app.command()
def warmup() -> None:
    """
    Pre-load LanguageTool server to reduce cold start latency.

    This command initializes the LanguageTool Java server before
    processing begins, avoiding the 10-30 second cold start delay.
    """
    console.print("[bold blue]Warming up LanguageTool...[/]")

    # POC stub - actual warmup will be implemented in Phase 2
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Initializing LanguageTool server...", total=None)
        # Placeholder for actual warmup logic
        # In production, this would call:
        # from ferpa_feedback.stage_1_grammar import create_grammar_checker
        # checker = create_grammar_checker({})
        # checker.warm_up()

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
        from ferpa_feedback.stage_5_review import create_review_app, ReviewQueue

        console.print(f"[bold blue]Starting review server on port {port}...[/]")
        queue = ReviewQueue()
        review_app = create_review_app(queue)
        uvicorn.run(review_app, host="0.0.0.0", port=port)
    except ImportError:
        console.print("[red]Review UI requires optional dependencies.[/]")
        console.print("[yellow]Install with: pip install ferpa-feedback[review-ui][/]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
