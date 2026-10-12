"""Scheduler task registry — single authoritative source of task definitions.

Each task entry defines:
  - name: task_name used for Redis ctrl/lock/heartbeat keys and cli trigger.
  - display_name: human-readable name surfaced by the system and manage.sh.
  - interval_key: system_config key for a configurable interval (None = fixed interval).
  - default_interval: fallback/default interval in seconds.
"""

SCHEDULER_TASKS = [
    {"name": "firewall_query",          "display_name": "Blacklist Expiry Cleanup", "interval_key": "scheduler_firewall_query_interval",      "default_interval": 3600},
    {"name": "arp_collection",          "display_name": "ARP Data Collection",       "interval_key": "scheduler_arp_collection_interval",      "default_interval": 300},
    {"name": "ipguard_sync",            "display_name": "Compliance Baseline Sync",  "interval_key": "scheduler_ipguard_sync_interval",        "default_interval": 600},
    {"name": "compliance_check",        "display_name": "Compliance Check",          "interval_key": "scheduler_compliance_check_interval",    "default_interval": 300},
    {"name": "auto_unblock",            "display_name": "Auto Unblock",              "interval_key": "scheduler_auto_unblock_interval",        "default_interval": 600},
    {"name": "log_cleanup",             "display_name": "Log Cleanup",               "interval_key": None,                                     "default_interval": 86400},
    {"name": "firewall_reconciliation", "display_name": "Firewall Reconciliation",   "interval_key": None,                                     "default_interval": 300},
    {"name": "backup",                  "display_name": "Scheduled Backup",          "interval_key": None,                                     "default_interval": 60},
]