# -*- coding: utf-8 -*-
"""
芽课 · 每日推送正文生成器

读 05-工作台成品/payload.json，输出一封手机上能一屏读完的纯文本邮件。
只做一件事：把今天该读的那 1 篇、该问的那 1 句、该做的 1 个动作推到眼前。

用法：
    python notify.py            # 生成并打印
    python notify.py --write    # 同时写到 05-工作台成品/今日推送.md
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PAYLOAD = os.path.join(HERE, '..', '05-工作台成品', 'payload.json')
OUT = os.path.join(HERE, '..', '05-工作台成品', '今日推送.md')
LINK = 'https://workbuddy.link/p/AlPsT5FPs8TiRhiMeGNtZc#today'


def short_date(d):
    # "2026-11-03" -> "11-03"
    return d[5:] if d and len(d) >= 10 else (d or '')


def build():
    with io.open(PAYLOAD, encoding='utf-8') as f:
        d = json.load(f)

    gen = short_date(d.get('generated', '')[:10])
    t3 = d.get('today3') or {}
    r = t3.get('read')
    doing = t3.get('doing')
    review = t3.get('review')
    overdue = d.get('overdue') or []

    subject = '芽课 · 今天一件事'
    if r and r.get('gridName'):
        subject = '芽课 · ' + r['gridName'].split('：')[0][:18]

    L = []
    L.append('今天只做一件事：读下面这篇，然后说一句你不同意的话。')
    L.append('')

    if r:
        L.append('【1 篇 · %s · 第 %d/%d 格】' % (r.get('domain', ''), r.get('grid', 0), r.get('gridTotal', 0)))
        L.append(r.get('gridName', ''))
        L.append('')
        if r.get('brief'):
            L.append(r['brief'])
            L.append('')
        L.append('笔记在 %s（%s 字，%s 条来源）。' % (
            r.get('date', ''), r.get('chars', 0), r.get('sources', 0)))
    else:
        L.append('素材包里没有可推荐的日记 —— 先去看运维页，任务可能没跑。')

    L.append('')
    L.append('——')
    L.append('')

    L.append('【今天问你一句】')
    L.append('这篇里哪一句你觉得「太理想化 / 跟我做过的对不上 / 太抽象」？')
    L.append('想到就回我一句，三十秒的事。不肯定的地方比确定的地方值钱。')
    L.append('')

    if doing and doing.get('items'):
        L.append('【顺手做 1 个】%s' % doing.get('domain', ''))
        L.append('· ' + doing['items'][0])
        extra = len(doing['items']) - 1
        if extra > 0:
            L.append('　另外 %d 条在页面里。' % extra)
        L.append('')

    if review:
        age = review.get('age') or 0
        L.append('【顺手复习】%s · %s%s' % (
            review.get('name', ''), review.get('domain', ''),
            ('　间隔 %d 天' % age) if age else '　高频概念'))
        L.append('')

    L.append('——')
    L.append('')
    L.append('打开工作台：' + LINK)
    L.append('')

    if overdue:
        parts = []
        for o in overdue:
            gap = o.get('gapDays') or 0
            if not o.get('lastOk'):
                tag = '从未产出'
            elif gap > 0:
                tag = '停 %d 天' % gap
            else:
                tag = '今天没产出'
            parts.append('%s（%s）' % (o.get('domain', ''), tag))
        L.append('⚠ %d 个任务该跑没跑：%s' % (len(overdue), ' · '.join(parts)))
        L.append('　这不影响你今天读什么，但连续断供会让后面几格的进度越拖越远。')
        L.append('')

    L.append('快照 %s' % gen)
    return subject, '\n'.join(L)


def main():
    subject, body = build()
    text = '主题：' + subject + '\n\n' + body
    print(text)
    if '--write' in sys.argv:
        with io.open(OUT, 'w', encoding='utf-8') as f:
            f.write(text)
        print('\n[已写入] ' + OUT)


if __name__ == '__main__':
    main()
