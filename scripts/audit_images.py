#!/usr/bin/env python3
"""Run trusted image audit and write download/_work/suspect_existing_images.csv."""
from scrape_images_trusted import setup_logging, audit_existing

if __name__ == "__main__":
    setup_logging()
    audit_existing()
