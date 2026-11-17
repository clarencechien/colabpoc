#!/usr/bin/env bash
# CC session 開頭固定動作。用 source 執行。不印憑證內容。
export PATH="$PATH:$HOME/.local/bin"
command -v colab >/dev/null || uv tool install google-colab-cli
if [ -z "${COLAB_ADC_JSON:-}" ]; then
  echo "COLAB_ADC_JSON 沒設：CLI 路線不能用（見 docs/handoff.md 2.1）" >&2
  return 1 2>/dev/null || exit 1
fi
( umask 077; mkdir -p ~/.config/gcloud; printf '%s' "$COLAB_ADC_JSON" > ~/.config/gcloud/application_default_credentials.json )
export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/application_default_credentials.json
[ -f ~/.ssh/id_ed25519 ] || ssh-keygen -q -t ed25519 -N '' -f ~/.ssh/id_ed25519
echo "colab CLI $(colab version 2>/dev/null | head -1) ready; 每個指令記得加 --auth=adc"
