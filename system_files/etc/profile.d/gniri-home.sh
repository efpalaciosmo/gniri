#!/usr/bin/env bash
# Fedora bootc exposes /var/home through /home. Keep the logical home spelling
# for prompts when a terminal starts in the same directory via its physical path.
case $- in
    *i*)
        if [[ -n ${HOME:-} && ${PWD:-} != "$HOME" && $PWD -ef $HOME ]]; then
            cd -L -- "$HOME" || return
        fi
        ;;
esac
