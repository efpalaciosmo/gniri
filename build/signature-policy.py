#!/usr/bin/env python3
"""Separate bootc's deny-by-default trust from general-purpose container policy."""
import copy


def signature_policies(original, repository):
    rule = [{'type': 'sigstoreSigned', 'keyPath': '/usr/share/gniri/keys/cosign.pub',
             'signedIdentity': {'type': 'matchRepository'}}]
    general = copy.deepcopy(original)
    general.setdefault('transports', {}).setdefault('docker', {})[repository] = rule
    # bootc rejects a global insecureAcceptAnything default in enforced mode.
    # Do not solve that by breaking unrelated Podman/Distrobox image pulls.
    bootc = {'default': [{'type': 'reject'}], 'transports': {'docker': {repository: rule}}}
    return general, bootc
