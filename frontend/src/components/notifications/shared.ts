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
    {
      key: 'mode',
      label: 'Mode',
      type: 'select',
      options: [
        { value: 'webhook', label: 'Webhook Robot' },
        { value: 'app', label: 'App Message' },
      ],
      defaultValue: 'webhook',
    },
    { key: 'webhook_url', label: 'Webhook URL', type: 'text', placeholder: 'https://open.feishu.cn/...', showWhen: { mode: 'webhook' } },
    { key: 'app_id', label: 'App ID', type: 'text', placeholder: 'cli_xxx', showWhen: { mode: 'app' } },
    { key: 'app_secret', label: 'App Secret', type: 'password', placeholder: '********', showWhen: { mode: 'app' } },
    {
      key: 'receive_id_type',
      label: 'Receive ID Type',
      type: 'select',
      options: [
        { value: 'open_id', label: 'Open ID' },
        { value: 'user_id', label: 'User ID' },
        { value: 'chat_id', label: 'Chat ID' },
        { value: 'department_id', label: 'Department ID' },
        { value: 'email', label: 'Email' },
      ],
      defaultValue: 'open_id',
      showWhen: { mode: 'app' },
    },
    { key: 'receive_id', label: 'Receive ID', type: 'text', placeholder: 'ou_xxx / on_xxx / oc_xxx', showWhen: { mode: 'app' } },
  ],
  dingtalk: [
    {
      key: 'mode',
      label: 'Mode',
      type: 'select',
      options: [
        { value: 'webhook', label: 'Webhook Robot' },
        { value: 'app', label: 'App Message' },
      ],
      defaultValue: 'webhook',
    },
    { key: 'webhook_url', label: 'Webhook URL', type: 'text', placeholder: 'https://oapi.dingtalk.com/...', showWhen: { mode: 'webhook' } },
    { key: 'secret', label: 'Sign Secret', type: 'password', placeholder: '********', showWhen: { mode: 'webhook' } },
    { key: 'app_key', label: 'App Key', type: 'text', placeholder: 'dingxxx', showWhen: { mode: 'app' } },
    { key: 'app_secret', label: 'App Secret', type: 'password', placeholder: '********', showWhen: { mode: 'app' } },
    { key: 'agent_id', label: 'Agent ID', type: 'text', placeholder: '123456789', showWhen: { mode: 'app' } },
    { key: 'userid_list', label: 'User ID List', type: 'text', placeholder: 'user1,user2', showWhen: { mode: 'app' } },
    { key: 'dept_id_list', label: 'Dept ID List', type: 'text', placeholder: '100,200', showWhen: { mode: 'app' } },
    {
      key: 'to_all_user',
      label: 'To All User',
      type: 'select',
      options: [
        { value: 'false', label: 'No' },
        { value: 'true', label: 'Yes' },
      ],
      defaultValue: 'false',
      showWhen: { mode: 'app' },
    },
  ],
  wecom: [
    {
      key: 'mode',
      label: 'Mode',
      type: 'select',
      options: [
        { value: 'webhook', label: 'Webhook Robot' },
        { value: 'app', label: 'App Message' },
      ],
      defaultValue: 'webhook',
    },
    { key: 'webhook_url', label: 'Webhook URL', type: 'text', placeholder: 'https://qyapi.weixin.qq.com/...', showWhen: { mode: 'webhook' } },
    { key: 'corp_id', label: 'Corp ID', type: 'text', placeholder: 'ww1234567890', showWhen: { mode: 'app' } },
    { key: 'agent_id', label: 'Agent ID', type: 'text', placeholder: '1000002', showWhen: { mode: 'app' } },
    { key: 'secret', label: 'Secret', type: 'password', placeholder: '********', showWhen: { mode: 'app' } },
    { key: 'touser', label: 'To User', type: 'text', placeholder: 'UserID1|UserID2', showWhen: { mode: 'app' } },
    { key: 'toparty', label: 'To Party', type: 'text', placeholder: 'PartyID1|PartyID2', showWhen: { mode: 'app' } },
    { key: 'totag', label: 'To Tag', type: 'text', placeholder: 'TagID1|TagID2', showWhen: { mode: 'app' } },
  ],
};
