// ---------------------------------------------------------------------------
// Shared config field registry for Notification channel types
// Mirrors the datasources/shared.ts ConfigFieldDef pattern.
// Backend source of truth: CHANNEL_METADATA in
// backend/app/services/notification_channels/event_types.py
// ---------------------------------------------------------------------------

import { ConfigFieldDef } from '@/components/datasources/shared';

export const CHANNEL_CONFIG_FIELDS: Record<string, ConfigFieldDef[]> = {
  email: [
    {
      key: 'recipients',
      label: 'Recipients',
      type: 'text',
      placeholder: 'user1@example.com, user2@example.com',
    },
  ],
  webhook: [
    { key: 'url', label: 'Webhook URL', type: 'text', placeholder: 'https://...' },
    {
      key: 'method',
      label: 'HTTP Method',
      type: 'select',
      options: [
        { value: 'POST', label: 'POST' },
        { value: 'PUT', label: 'PUT' },
        { value: 'PATCH', label: 'PATCH' },
      ],
      defaultValue: 'POST',
    },
    {
      key: 'headers',
      label: 'Custom Headers (JSON)',
      type: 'text',
      placeholder: '{"X-Custom": "value"}',
    },
    { key: 'secret', label: 'HMAC Secret', type: 'password', placeholder: '********' },
  ],
  feishu: [
    { key: 'webhook_url', label: 'Webhook URL', type: 'text', placeholder: 'https://open.feishu.cn/...' },
  ],
  dingtalk: [
    { key: 'webhook_url', label: 'Webhook URL', type: 'text', placeholder: 'https://oapi.dingtalk.com/...' },
    { key: 'secret', label: 'Sign Secret', type: 'password', placeholder: '********' },
  ],
  wecom: [
    { key: 'webhook_url', label: 'Webhook URL', type: 'text', placeholder: 'https://qyapi.weixin.qq.com/...' },
  ],
};
