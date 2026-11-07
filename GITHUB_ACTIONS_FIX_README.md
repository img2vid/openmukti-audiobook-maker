# Complete Openmukti Audiobook Maker 1.2.0 - GitHub Actions repair

This is the complete original project archive, not just a patch. The full
openvoice/engines and openvoice/resources directories, including bundled fonts
and compressed dictionaries, are included. The GitHub Actions build workflow
now checks for missing assets before installing dependencies and testing.

To update GitHub Actions, extract this ZIP, enter its single top-level project
folder, then commit and push all files to the GitHub repository:

    git add -A
    git status --short
    git commit -m "Restore Openmukti speech engines and bundled assets"
    git push origin main

Verify before pushing:

    python scripts/verify_repository_assets.py
    python -m unittest discover -s tests -p "test_cli_new_commands.py" -v
    python -m unittest discover -s tests -p "test_device_and_workflows.py" -v
    python -m unittest discover -s tests -p "test_dialogue_analysis.py" -v

IMPORTANT: GitHub Actions uses the repository files checked out from GitHub.
Uploading this ZIP as a release or Actions artifact by itself does not repair
the source repository. Extract its contents and commit/push them.

The repair has been checked locally; complete Windows/ARM/Linux/macOS release
builds have not been verified.
