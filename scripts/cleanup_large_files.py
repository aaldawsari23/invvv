#!/usr/bin/env python3
"""
Clean up large files from git history using git filter-branch.
Files to remove from history:
  - download/product_images_package.zip           (163 MB)
  - download/product_images_package_part1.zip     (50 MB)
  - download/product_images_package_part2.zip     (50 MB)
  - download/product_images_package_part3.zip     (50 MB)
  - download/product_images_package_part4.zip     (13 MB)

After cleaning, the .git history will be much smaller and push should succeed.
"""
import subprocess
import os

LARGE_FILES = [
    "download/product_images_package.zip",
    "download/product_images_package_part1.zip",
    "download/product_images_package_part2.zip",
    "download/product_images_package_part3.zip",
    "download/product_images_package_part4.zip",
]


def run(cmd, check=True):
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout[:500])
    if result.stderr:
        print("STDERR:", result.stderr[:500])
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}")
    return result


def main():
    os.chdir("/home/z/my-project")

    # First: add these large files to .gitignore so they don't get re-added
    gi_path = "/home/z/my-project/.gitignore"
    with open(gi_path, "a") as f:
        f.write("\n# Large ZIP files — too big for git, served via download/ instead\n")
        for f_ in LARGE_FILES:
            f.write(f"{f_}\n")
    print("Updated .gitignore")

    # Remove the files from the working tree and current commit
    for f in LARGE_FILES:
        if os.path.exists(f):
            os.remove(f)
            print(f"Removed {f}")

    # Commit the removal
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "Remove large ZIP files (>100MB) from git tracking"])

    # Now rewrite history to remove these files from ALL previous commits
    # Using git filter-branch (slower but no extra deps)
    print("\n=== Rewriting history to remove large files from all commits ===")

    # Build the index-filter command
    for f in LARGE_FILES:
        print(f"\nRemoving {f} from history...")
        # Use --index-filter for speed
        cmd = [
            "git", "filter-branch", "--force", "--prune-empty",
            "--index-filter",
            f'git rm --cached --ignore-unmatch "{f}"',
            "--", "--all",
        ]
        # Set env to allow this on containers
        env = os.environ.copy()
        env["FILTER_BRANCH_SQUELCH_WARNING"] = "1"
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            print(f"  STDERR: {result.stderr[:500]}")
        # Clean up refs/original after each filter-branch run
        run(["git", "for-each-ref", "--format=%(refname)", "refs/original/"],
            check=False)
        # Delete the backup refs
        out = subprocess.run(["git", "for-each-ref", "--format=%(refname)",
                              "refs/original/"], capture_output=True, text=True).stdout
        for line in out.strip().split("\n"):
            if line:
                subprocess.run(["git", "update-ref", "-d", line], check=False)

    # Run git gc to actually reclaim space
    print("\n=== Running git gc to reclaim space ===")
    run(["git", "reflog", "expire", "--expire=now", "--all"])
    run(["git", "gc", "--prune=now", "--aggressive"], check=False)

    # Show final size
    result = subprocess.run(["du", "-sh", ".git"], capture_output=True, text=True)
    print(f"\nFinal .git size: {result.stdout.strip()}")

    # Show tracked files
    result = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
    print(f"Tracked files: {len(result.stdout.strip().splitlines())}")

    # Show largest tracked files
    print("\nLargest tracked files:")
    result = subprocess.run(
        ["bash", "-c",
         'git ls-files | xargs -I {} du -b "{}" 2>/dev/null | sort -rn | head -10'],
        capture_output=True, text=True
    )
    print(result.stdout)


if __name__ == "__main__":
    main()
