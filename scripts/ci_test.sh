#!/usr/bin/env bash
set -Eeuo pipefail

suite="${1:-framework}"
marker="${2:-smoke}"
workers="${3:-auto}"

mkdir -p allure-results

case "$suite" in
  framework)
    python -m pytest framework_tests -m framework \
      --alluredir=allure-results --junitxml=junit-framework.xml \
      --html=reports/framework.html --self-contained-html
    ;;
  e2e)
    python -m pytest tests -m "$marker" -n "$workers" \
      --alluredir=allure-results --junitxml=junit-e2e.xml \
      --html=reports/e2e.html --self-contained-html
    ;;
  *)
    echo "Usage: $0 [framework|e2e] [pytest-marker] [xdist-workers]" >&2
    exit 2
    ;;
esac
