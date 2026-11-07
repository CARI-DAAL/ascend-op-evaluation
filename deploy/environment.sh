#!/usr/bin/env bash
# Normalize deployment settings without evaluating values or printing credentials.
# Source before using settings, and again after loading an operator-owned env file.
while IFS= read -r setting; do
  case "$setting" in
    TRITON_EVAL_*)
      replacement="ASCEND_OP_EVAL_${setting#TRITON_EVAL_}"
      if [[ -v "$replacement" && "${!replacement}" != "${!setting}" ]]; then
        echo "Conflicting settings: $setting and $replacement" >&2
        return 2 2>/dev/null || exit 2
      fi
      export "$replacement=${!setting}"
      ;;
  esac
done < <(compgen -e)
unset setting replacement
