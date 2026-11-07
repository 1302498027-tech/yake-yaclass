# -*- coding: utf-8 -*-
"""
芽课 · 每日一条线

重建索引 → 重建页面 → 重新发布 → 生成推送正文。

一条命令跑完，供每天早上的自动化调用。任何一步失败不中断，
把问题记在末尾（发邮件比修页面重要）。

用法：
    python daily_push.py               # 全跑
    python daily_push.py --no-publish  # 只重建本地页面，不碰线上
    python daily_push.py --body-only   # 只生成推送正文（用现有 payload）
"""
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.abspath(os.path.join(HERE, '..', '05-工作台成品', '芽课个人工作库.html'))
SKILL = r'C:\Program Files\WorkBuddy\resources\app.asar.unpacked\resources\plugins\workbuddy-builtin\skills\library'
NODE = 'AlPsT5FPs8TiRhiMeGNtZc'
DBID = 'YkMcLJUZ8vqF4BrazXmoKd'

issues = []


def run(label, args, cwd=None, need=None):
    """跑一步，失败只记问题不中断。need = 输出里必须出现的标记。"""
    try:
        r = subprocess.run(
            [sys.executable] + args, cwd=cwd or HERE,
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)
    except Exception as e:
        issues.append('%s 调用失败：%s' % (label, e))
        return ''
    out = (r.stdout or '') + (r.stderr or '')
    if r.returncode != 0:
        issues.append('%s 退出码 %d：%s' % (label, r.returncode, out.strip()[-300:]))
    elif need and need not in out:
        issues.append('%s 输出里没有 %s：%s' % (label, need, out.strip()[-300:]))
    return out


def main():
    body_only = '--body-only' in sys.argv
    publish = '--no-publish' not in sys.argv and not body_only

    if not body_only:
        run('扫素材包', ['ingest.py'], need='payload')
        run('构建页面', ['build_workbench.py', '--no-ingest'], need='输出')

    if publish:
        run('导入线上', [os.path.join(SKILL, 'page', 'import_html.py'), HTML,
                        '--node-block-id', NODE, '--databases', '[{"id":"%s"}]' % DBID],
            cwd=SKILL, need='KS_IMPORT_OK')
        out = run('发布', [os.path.join(SKILL, 'page', 'publish_page.py'), '--node-id', NODE],
                  cwd=SKILL, need='KS_PAGE_PUBLISH')
        for line in out.splitlines():
            if line.startswith('KS_PAGE_PUBLISH'):
                print('已上线 ' + line.split('\t')[-1].strip())

    body = run('生成正文', ['notify.py', '--write'], need='主题')

    if issues:
        print('\n【本次没做成的】')
        for x in issues:
            print('- ' + x)
        print('')

    print('=== 邮件正文开始 ===')
    print(body.strip())
    print('=== 邮件正文结束 ===')


if __name__ == '__main__':
    main()
