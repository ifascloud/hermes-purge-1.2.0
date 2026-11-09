/**
 * hermes-purge 桌面状态栏面板。
 *
 * 数据来源：`host.request('cli.exec', { argv: ['purge', 'status', '--json'] })`
 * —— 与 /purge 命令同一条 CLI 逻辑，面板不另写一套读取代码，
 *    因此面板显示的值永远是 `hermes purge status` 会打印的值。
 *
 * 保存位置：<hermes home>/desktop-plugins/hermes-purge/plugin.js（文件夹名 == id）
 * 源码位置：<hermes home>/src/hermes-purge/desktop/plugin.js（git）
 */

import {
  Button,
  Popover,
  PopoverContent,
  PopoverTrigger,
  STATUSBAR_AREAS,
  StatusDot,
  Switch,
  Tip,
  cn,
  haptic,
  host,
  useMutation,
  usePluginI18n,
  useQuery,
  useQueryClient
} from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'hermes-purge'
const QUERY_KEY = ['hermes-purge', 'status']

const LOCALES = {
  zh: {
    title: '执行姿态层',
    on: '开',
    off: '关',
    unknown: '未知',
    inject: '注入到新会话',
    rules: '规则',
    snapshots: '快照',
    latest: '最新',
    config: '配置',
    model: '模型',
    dir: '目录',
    refresh: '刷新',
    snapshot: '建快照',
    none: '尚无',
    hint: '改规则或开关后，/new 才生效',
    chipOn: 'purge',
    chipOff: 'purge 关',
    chipError: 'purge 不可用',
    chipTip: 'Hermes 执行姿态层：点开查看规则、快照与注入开关',
    snapDone: '快照已建立',
    toggleDone: '注入已切换（新会话生效）',
    failed: '操作失败'
  },
  en: {
    title: 'Execution posture',
    on: 'on',
    off: 'off',
    unknown: 'unknown',
    inject: 'Inject into new sessions',
    rules: 'Rules',
    snapshots: 'Snapshots',
    latest: 'latest',
    config: 'Config',
    model: 'Model',
    dir: 'Dir',
    refresh: 'Refresh',
    snapshot: 'Snapshot',
    none: 'none',
    hint: 'Rules and toggles apply to new sessions (/new)',
    chipOn: 'purge',
    chipOff: 'purge off',
    chipError: 'purge unavailable',
    chipTip: 'Hermes execution-posture layer: rules, snapshots, injection toggle',
    snapDone: 'Snapshot created',
    toggleDone: 'Injection toggled (applies to new sessions)',
    failed: 'Action failed'
  }
}

// 磁盘插件不被 Tailwind 扫描：只写布局，颜色一律走主题变量。
const CSS = `
.hpurge-chip{display:inline-flex;align-items:center;gap:4px;height:100%;white-space:nowrap}
.hpurge-chip-text{font-variant-numeric:tabular-nums;letter-spacing:.01em}
.hpurge-panel{width:286px;max-width:calc(100vw - 24px);font-size:12px;line-height:17px}
.hpurge-panel-head{display:flex;align-items:center;gap:6px;padding:2px 2px 6px}
.hpurge-title{font-weight:500;color:var(--ui-text-primary)}
.hpurge-state{margin-left:auto;color:var(--ui-text-tertiary);font-variant-numeric:tabular-nums}
.hpurge-row{display:flex;align-items:baseline;gap:8px;padding:2px 2px}
.hpurge-row-label{flex:none;width:64px;color:var(--ui-text-tertiary)}
.hpurge-row-value{flex:1;min-width:0;color:var(--ui-text-secondary);overflow-wrap:anywhere}
.hpurge-row-value[data-mono=true]{font-family:var(--font-mono,monospace);font-size:11px}
.hpurge-switch-row{display:flex;align-items:center;gap:8px;padding:4px 2px 6px}
.hpurge-sep{height:1px;margin:4px 0;background:var(--ui-stroke-secondary);opacity:.6}
.hpurge-actions{display:flex;gap:4px;padding:6px 0 2px}
.hpurge-foot{padding:4px 2px 0;color:var(--ui-text-quaternary);font-size:11px;line-height:15px}
.hpurge-error{color:var(--ui-text-secondary);padding:2px 2px 6px}
`

function parseJsonLoose(text) {
  const raw = String(text || '')
  const start = raw.indexOf('{')
  const end = raw.lastIndexOf('}')
  if (start < 0 || end <= start) throw new Error('no JSON payload')
  return JSON.parse(raw.slice(start, end + 1))
}

async function runCli(argv) {
  const result = await host.request('cli.exec', { argv })
  if (result?.blocked || result?.code !== 0) {
    throw new Error(result?.hint || result?.output || `hermes ${argv.join(' ')} failed`)
  }
  return result
}

async function fetchStatus() {
  const result = await runCli(['purge', 'status', '--json'])
  return parseJsonLoose(result.output)
}

function fmtChars(chars, limit) {
  const value = Number(chars)
  if (!Number.isFinite(value)) return '—'
  const shown = value >= 1000 ? `${(value / 1000).toFixed(1)}k` : String(value)
  return limit ? `${shown}/${limit}` : shown
}

function Row({ label, value, mono }) {
  return jsxs('div', {
    className: 'hpurge-row',
    children: [
      jsx('span', { className: 'hpurge-row-label', children: label }),
      jsx('span', {
        className: 'hpurge-row-value',
        'data-mono': mono ? 'true' : 'false',
        children: value
      })
    ]
  })
}

function Panel({ status, error, onToggle, onSnapshot, onRefresh, busy, t }) {
  if (error && !status) {
    return jsxs('div', {
      className: 'hpurge-panel',
      children: [
        jsx('div', { className: 'hpurge-panel-head', children: jsx('span', { className: 'hpurge-title', children: t('title') }) }),
        jsx('div', { className: 'hpurge-error', children: `${t('chipError')}: ${error}` }),
        jsx('div', {
          className: 'hpurge-actions',
          children: jsx(Button, { variant: 'ghost', size: 'micro', onClick: onRefresh, children: t('refresh') })
        })
      ]
    })
  }
  const enabled = Boolean(status?.enabled)
  const overLimit = Number(status?.chars) > Number(status?.limit)
  const snapshots = Number(status?.snapshots || 0)

  return jsxs('div', {
    className: 'hpurge-panel',
    children: [
      jsxs('div', {
        className: 'hpurge-panel-head',
        children: [
          jsx(StatusDot, { tone: !status ? 'muted' : overLimit ? 'warn' : enabled ? 'good' : 'muted' }),
          jsx('span', { className: 'hpurge-title', children: t('title') }),
          jsx('span', {
            className: 'hpurge-state',
            children: status ? (enabled ? t('on') : t('off')) : t('unknown')
          })
        ]
      }),
      jsxs('div', {
        className: 'hpurge-switch-row',
        children: [
          jsx('span', { className: 'hpurge-row-label', style: { width: 'auto', flex: '1' }, children: t('inject') }),
          jsx(Switch, {
            checked: enabled,
            disabled: busy || !status,
            size: 'xs',
            'aria-label': t('inject'),
            onCheckedChange: next => onToggle(Boolean(next))
          })
        ]
      }),
      jsx('div', { className: 'hpurge-sep' }),
      jsxs('div', {
        children: [
          Row({
            label: t('rules'),
            value: status ? `${status.rules} · ${fmtChars(status.chars, status.limit)}` : '—'
          }),
          Row({
            label: t('snapshots'),
            value: status
              ? snapshots > 0
                ? `${snapshots} · ${t('latest')} ${String(status.last_snapshot || '').replace(/^\d{8}T\d{6}Z-?/, '') || '—'}`
                : t('none')
              : '—',
            mono: false
          }),
          Row({
            label: t('config'),
            value: status ? `max_turns ${status.max_turns ?? '—'} · approvals ${status.approval_mode ?? '—'}` : '—'
          }),
          Row({ label: t('model'), value: status?.model || '—', mono: true })
        ]
      }),
      jsx('div', { className: 'hpurge-sep' }),
      jsxs('div', {
        className: 'hpurge-actions',
        children: [
          jsx(Button, { variant: 'ghost', size: 'micro', onClick: onRefresh, disabled: busy, children: t('refresh') }),
          jsx(Button, { variant: 'ghost', size: 'micro', onClick: onSnapshot, disabled: busy, children: t('snapshot') })
        ]
      }),
      jsx('div', { className: 'hpurge-foot', children: t('hint') })
    ]
  })
}

function PurgeChip() {
  const t = usePluginI18n(ID)
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)

  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchStatus,
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 0
  })

  const toggle = useMutation({
    mutationFn: next => runCli(['purge', next ? 'on' : 'off']),
    onSuccess: () => {
      haptic('tap')
      host.notify({ kind: 'info', message: t('toggleDone') })
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
    onError: err => host.notify({ kind: 'error', message: `${t('failed')}: ${err?.message || err}` })
  })

  const snapshot = useMutation({
    mutationFn: () => runCli(['purge', 'snapshot', 'widget']),
    onSuccess: () => {
      host.notify({ kind: 'info', message: t('snapDone') })
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
    onError: err => host.notify({ kind: 'error', message: `${t('failed')}: ${err?.message || err}` })
  })

  const status = query.data
  const enabled = Boolean(status?.enabled)
  const overLimit = Number(status?.chars) > Number(status?.limit)
  const error = query.error ? String(query.error.message || query.error) : null
  const busy = toggle.isPending || snapshot.isPending

  const label = error && !status
    ? t('chipError')
    : !status
      ? t('chipOn')
      : enabled
        ? `${t('chipOn')} ${fmtChars(status.chars)}`
        : t('chipOff')

  const tone = error && !status ? 'warn' : !status ? 'muted' : overLimit ? 'warn' : enabled ? 'good' : 'muted'

  return jsx(Tip, {
    label: t('chipTip'),
    children: jsxs(Popover, {
      open,
      onOpenChange: setOpen,
      children: [
        jsx(PopoverTrigger, {
          asChild: true,
          children: jsxs(Button, {
            variant: 'ghost',
            size: 'micro',
            className: 'hpurge-chip',
            'aria-label': `${t('title')}: ${label}`,
            children: [
              jsx(StatusDot, { tone }),
              jsx('span', { className: 'hpurge-chip-text', children: label })
            ]
          })
        }),
        jsx(PopoverContent, {
          side: 'top',
          align: 'end',
          className: 'hpurge-panel',
          'aria-label': t('title'),
          children: jsx(Panel, {
            status,
            error,
            busy,
            t,
            onToggle: next => toggle.mutate(next),
            onSnapshot: () => snapshot.mutate(),
            onRefresh: () => void queryClient.invalidateQueries({ queryKey: QUERY_KEY })
          })
        })
      ]
    })
  })
}

export default {
  id: ID,
  name: 'hermes-purge',
  description: '执行姿态层状态栏面板：注入开关、规则字符数、快照与关键配置，点开可切换 /purge。',
  register(ctx) {
    ctx.i18n.register(LOCALES)

    const style = document.createElement('style')
    style.textContent = CSS
    document.head.append(style)
    ctx.onDispose(() => style.remove())

    ctx.register({
      id: 'chip',
      area: STATUSBAR_AREAS.right,
      order: 9,
      render: () => jsx(PurgeChip, {})
    })
  }
}
