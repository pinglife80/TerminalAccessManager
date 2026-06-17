import { describe, it, expect } from 'vitest'
import {
  formatDate,
  formatDateTime,
  validateMACAddress,
  validateIPAddress,
  truncateText,
  capitalize,
  normalizeMacAddress,
  isValidMacAddress,
  isValidIpAddress,
  isValidCidrOrRange,
  getErrorMessage,
} from '../utils'

describe('formatDate', () => {
  it('should return "-" for null input', () => {
    expect(formatDate(null)).toBe('-')
  })

  it('should return "-" for undefined input', () => {
    expect(formatDate(undefined)).toBe('-')
  })

  it('should format a valid date string', () => {
    const result = formatDate('2024-01-15T10:30:00Z')
    expect(result).not.toBe('-')
    expect(typeof result).toBe('string')
  })

  it('should return original string for invalid date', () => {
    expect(formatDate('not-a-date')).toBe('not-a-date')
  })
})

describe('formatDateTime', () => {
  it('should return "-" for null input', () => {
    expect(formatDateTime(null)).toBe('-')
  })

  it('should format a valid date string to ISO format', () => {
    const result = formatDateTime('2024-01-15T10:30:00Z')
    expect(result).toContain('2024-01-15')
    expect(result).toContain('10:30:00')
  })

  it('should return original string for invalid date', () => {
    expect(formatDateTime('invalid')).toBe('invalid')
  })
})

describe('validateMACAddress', () => {
  it('should validate a correct MAC address with colons', () => {
    expect(validateMACAddress('00:1A:2B:3C:4D:5E')).toBe(true)
  })

  it('should validate a correct MAC address with dashes', () => {
    expect(validateMACAddress('00-1A-2B-3C-4D-5E')).toBe(true)
  })

  it('should reject an invalid MAC address', () => {
    expect(validateMACAddress('invalid')).toBe(false)
  })

  it('should reject a partial MAC address', () => {
    expect(validateMACAddress('00:1A:2B')).toBe(false)
  })
})

describe('validateIPAddress', () => {
  it('should validate a correct IP address', () => {
    expect(validateIPAddress('192.168.1.1')).toBe(true)
  })

  it('should validate 0.0.0.0', () => {
    expect(validateIPAddress('0.0.0.0')).toBe(true)
  })

  it('should validate 255.255.255.255', () => {
    expect(validateIPAddress('255.255.255.255')).toBe(true)
  })

  it('should reject an invalid IP address', () => {
    expect(validateIPAddress('256.1.1.1')).toBe(false)
  })

  it('should reject a non-IP string', () => {
    expect(validateIPAddress('not-an-ip')).toBe(false)
  })
})

describe('truncateText', () => {
  it('should return empty string for empty input', () => {
    expect(truncateText('', 10)).toBe('')
  })

  it('should return original text if shorter than maxLength', () => {
    expect(truncateText('hello', 10)).toBe('hello')
  })

  it('should truncate text and add "..." if longer than maxLength', () => {
    expect(truncateText('hello world', 5)).toBe('hello...')
  })

  it('should return original text if equal to maxLength', () => {
    expect(truncateText('hello', 5)).toBe('hello')
  })
})

describe('capitalize', () => {
  it('should capitalize the first letter', () => {
    expect(capitalize('hello')).toBe('Hello')
  })

  it('should handle empty string', () => {
    expect(capitalize('')).toBe('')
  })

  it('should handle already capitalized string', () => {
    expect(capitalize('Hello')).toBe('Hello')
  })
})

describe('normalizeMacAddress', () => {
  it('should normalize a MAC address with colons', () => {
    expect(normalizeMacAddress('00:1A:2B:3C:4D:5E')).toBe('00-1A-2B-3C-4D-5E')
  })

  it('should normalize a MAC address without separators', () => {
    expect(normalizeMacAddress('001A2B3C4D5E')).toBe('00-1A-2B-3C-4D-5E')
  })

  it('should throw for invalid MAC address', () => {
    expect(() => normalizeMacAddress('invalid')).toThrow('Invalid MAC address format')
  })
})

describe('isValidMacAddress', () => {
  it('should return true for valid MAC address', () => {
    expect(isValidMacAddress('00:1A:2B:3C:4D:5E')).toBe(true)
  })

  it('should return true for MAC without separators', () => {
    expect(isValidMacAddress('001A2B3C4D5E')).toBe(true)
  })

  it('should return false for invalid MAC address', () => {
    expect(isValidMacAddress('invalid')).toBe(false)
  })

  it('should return false for partial MAC', () => {
    expect(isValidMacAddress('001A2B')).toBe(false)
  })
})

describe('isValidIpAddress', () => {
  it('should return true for valid IP', () => {
    expect(isValidIpAddress('192.168.1.1')).toBe(true)
  })

  it('should return false for invalid IP', () => {
    expect(isValidIpAddress('999.1.1.1')).toBe(false)
  })

  it('should return false for wrong number of octets', () => {
    expect(isValidIpAddress('192.168.1')).toBe(false)
  })
})

describe('isValidCidrOrRange', () => {
  it('should validate a CIDR notation', () => {
    expect(isValidCidrOrRange('192.168.1.0/24')).toBe(true)
  })

  it('should validate a plain IP address', () => {
    expect(isValidCidrOrRange('192.168.1.1')).toBe(true)
  })

  it('should reject invalid CIDR', () => {
    expect(isValidCidrOrRange('999.1.1.0/24')).toBe(false)
  })

  it('should reject empty string', () => {
    expect(isValidCidrOrRange('')).toBe(false)
  })
})

describe('getErrorMessage', () => {
  it('should extract detail from axios-style error', () => {
    const error = { response: { data: { detail: 'Unauthorized' } } }
    expect(getErrorMessage(error)).toBe('Unauthorized')
  })

  it('should extract message from axios-style error', () => {
    const error = { response: { data: { message: 'Forbidden' } } }
    expect(getErrorMessage(error)).toBe('Forbidden')
  })

  it('should return error.message for Error instances', () => {
    expect(getErrorMessage(new Error('test error'))).toBe('test error')
  })

  it('should return fallback for unknown errors', () => {
    expect(getErrorMessage('unknown')).toBe('An error occurred')
  })

  it('should return custom fallback message', () => {
    expect(getErrorMessage(null, 'Custom fallback')).toBe('Custom fallback')
  })
})
