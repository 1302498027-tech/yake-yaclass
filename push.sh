#!/bin/sh
# 把本仓库推到 GitHub。
#
#   用法：  ./push.sh <GitHub用户名> [仓库名]
#   默认仓库名：yake-yaclass
#
# 前提：.gitssh/id_ed25519.pub 已加到 GitHub → Settings → SSH and GPG keys，
#       且 GitHub 上已存在同名空仓库（不要勾 README / .gitignore / license）。
#
# 走的是 SSH 22 端口，不需要代理。
set -e
USER="${1:?用法: ./push.sh <GitHub用户名> [仓库名]}"
REPO="${2:-yake-yaclass}"
cd "$(dirname "$0")"

export GIT_SSH_COMMAND="ssh -i $(pwd)/.gitssh/id_ed25519 -o IdentitiesOnly=yes \
  -o UserKnownHostsFile=$(pwd)/.gitssh/known_hosts -o StrictHostKeyChecking=accept-new"

echo "==> 先验证密钥是否已被 GitHub 接受"
if ! ssh -T -o BatchMode=yes git@github.com 2>&1 | grep -q "successfully authenticated"; then
  echo "!! 密钥还没被 GitHub 认出来。请先把下面这行公钥加到 https://github.com/settings/keys"
  echo "   $(cat .gitssh/id_ed25519.pub)"
  exit 1
fi

git remote remove origin 2>/dev/null || true
git remote add origin "git@github.com:$USER/$REPO.git"
echo "==> 推送到 git@github.com:$USER/$REPO.git"
git push -u origin main
echo "==> 完成：https://github.com/$USER/$REPO"
