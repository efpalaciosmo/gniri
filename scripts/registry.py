#!/usr/bin/env python3
"""Resolve the Gniri Quay repository independently of the GitHub repository name."""
import argparse
import os
import re


def image_repository(repository, namespace=None):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Expected GitHub OWNER/REPOSITORY')
    namespace = namespace or os.environ.get('QUAY_NAMESPACE') or repository.split('/')[0].lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', namespace):
        raise ValueError('QUAY_NAMESPACE must be a lower-case Quay user or organization name')
    return f'quay.io/{namespace}/gniri'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository', help='GitHub OWNER/REPOSITORY')
    args = parser.parse_args()
    try:
        print(image_repository(args.repository))
    except ValueError as error:
        parser.error(str(error))
