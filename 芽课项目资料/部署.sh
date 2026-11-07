#!/bin/sh
# 芽课工作台 · 一键部署到腾讯云 CloudBase 静态托管
# 用法: sh 部署.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_ID="yake-pm-learn-d8gj30hst985e4f14"
TCB="$HOME/.dsh-tools/cloudbase/tcb"
SRC="$DIR/09-线上部署/芽课工作台-线上数据版.html"

[ -f "$SRC" ] || { echo "缺少 $SRC"; exit 1; }
mkdir -p "$DIR/09-线上部署/deploy"
cp "$SRC" "$DIR/09-线上部署/deploy/index.html"

echo "部署到 $ENV_ID ..."
"$TCB" hosting deploy "$DIR/09-线上部署/deploy" -e "$ENV_ID" --safe --verify
echo "完成: https://$ENV_ID-1491333553.tcloudbaseapp.com/"
