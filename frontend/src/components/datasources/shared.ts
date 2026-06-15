// ---------------------------------------------------------------------------
// Shared types, config, and helpers for DataSources tab components
// ---------------------------------------------------------------------------

export interface ConfigFieldDef {
  key: string;
  label: string;
  type: 'text' | 'password' | 'number' | 'select';
  placeholder?: string;
  options?: { value: string; label: string }[];
  defaultValue?: string;
  /** Only show this field when the condition matches (e.g., { auth_type: 'header' }) */
  showWhen?: Record<string, string>;
}

export const CONFIG_FIELDS: Record<string, ConfigFieldDef[]> = {
  arp_ssh: [
    { key: 'host', label: 'Host', type: 'text', placeholder: '192.168.1.1' },
    { key: 'port', label: 'Port', type: 'number', placeholder: '22', defaultValue: '22' },
    { key: 'username', label: 'Username', type: 'text', placeholder: 'root' },
    { key: 'password', label: 'Password', type: 'password', placeholder: '********' },
    { key: 'command', label: 'Command', type: 'text', placeholder: 'show arp' },
  ],
  arp_api: [
    { key: 'url', label: 'URL', type: 'text', placeholder: 'https://api.example.com/arp' },
    { key: 'method', label: 'Method', type: 'select', options: [{ value: 'GET', label: 'GET' }, { value: 'POST', label: 'POST' }], defaultValue: 'GET' },
    { key: 'auth_type', label: 'Auth Type', type: 'select', options: [{ value: 'none', label: 'None' }, { value: 'bearer', label: 'Bearer Token' }, { value: 'header', label: 'Custom Header' }, { value: 'basic', label: 'Basic Auth' }], defaultValue: 'none' },
    { key: 'header_name', label: 'Header Name', type: 'text', placeholder: 'X-Auth-Token', defaultValue: 'X-Auth-Token', showWhen: { auth_type: 'header' } },
    { key: 'token', label: 'Token / Password', type: 'password', placeholder: '********' },
    { key: 'headers', label: 'Extra Headers (JSON)', type: 'text', placeholder: '{"X-Custom": "value"}' },
  ],
  sangfor: [
    { key: 'base_url', label: 'Base URL', type: 'text', placeholder: 'https://sangfor.example.com' },
    { key: 'username', label: 'Username', type: 'text', placeholder: 'admin' },
    { key: 'password', label: 'Password', type: 'password', placeholder: '********' },
    { key: 'verify_ssl', label: 'Verify SSL', type: 'select', options: [{ value: 'true', label: 'Yes' }, { value: 'false', label: 'No' }], defaultValue: 'false' },
    { key: 'ca_bundle', label: 'CA Bundle Path', type: 'text', placeholder: '/path/to/ca-bundle.crt' },
  ],
};

export const TYPE_BADGE: Record<string, { label: string; className: string }> = {
  arp_ssh: { label: 'ARP SSH', className: 'bg-blue-100 text-blue-800' },
  arp_api: { label: 'ARP API', className: 'bg-green-100 text-green-800' },
  sangfor: { label: 'Sangfor', className: 'bg-orange-100 text-orange-800' },
};

export const BASELINE_CONFIG_FIELDS: Record<string, ConfigFieldDef[]> = {
  ipguard: [
    { key: 'db_type', label: 'Database Type', type: 'select', options: [
      { value: 'mssql', label: 'SQL Server' },
      { value: 'mysql', label: 'MySQL / MariaDB' },
      { value: 'postgresql', label: 'PostgreSQL' },
    ], defaultValue: 'mssql' },
    { key: 'host', label: 'Host', type: 'text', placeholder: '192.168.1.100' },
    { key: 'port', label: 'Port', type: 'number', placeholder: '1433', defaultValue: '1433' },
    { key: 'username', label: 'Username', type: 'text', placeholder: 'admin' },
    { key: 'password', label: 'Password', type: 'password', placeholder: '********' },
    { key: 'database', label: 'Database', type: 'text', placeholder: 'OCULAR3' },
  ],
};

export const BASELINE_TYPE_BADGE: Record<string, { label: string; className: string }> = {
  ipguard: { label: 'IP-Guard', className: 'bg-purple-100 text-purple-800' },
};

/**
 * Build a config object from form values, parsing JSON/number/boolean fields.
 */
export function buildConfigPayload(
  fields: ConfigFieldDef[],
  configValues: Record<string, string>,
): Record<string, string | number | boolean | object> {
  const config: Record<string, string | number | boolean | object> = {};
  fields.forEach((f) => {
    const val = configValues[f.key];
    if (val === undefined || val === '') return;
    if (f.key === 'headers' || f.key === 'port' || f.key === 'verify_ssl') {
      try {
        config[f.key] = JSON.parse(val);
      } catch {
        if (f.key === 'port') config[f.key] = Number(val);
        else if (f.key === 'verify_ssl') config[f.key] = val === 'true';
        else config[f.key] = val;
      }
    } else if (f.key === 'port') {
      config[f.key] = Number(val);
    } else {
      config[f.key] = val;
    }
  });
  return config;
}

/**
 * Populate config values from an existing data source / baseline object.
 */
export function populateConfigFromItem(
  fields: ConfigFieldDef[],
  rawConfig: Record<string, string | number | boolean | object | null | undefined>,
): Record<string, string> {
  const configVals: Record<string, string> = {};
  fields.forEach((f) => {
    const val = rawConfig[f.key];
    if (val === undefined || val === null) {
      configVals[f.key] = f.defaultValue || '';
    } else if (typeof val === 'object') {
      configVals[f.key] = JSON.stringify(val);
    } else {
      configVals[f.key] = String(val);
    }
  });
  return configVals;
}

/**
 * Get default config values for a given type.
 */
export function getDefaultConfig(fields: ConfigFieldDef[]): Record<string, string> {
  const defaults: Record<string, string> = {};
  fields.forEach((f) => {
    defaults[f.key] = f.defaultValue || '';
  });
  return defaults;
}
