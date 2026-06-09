import { describe, it, expect, beforeEach } from 'vitest'
import { useThemeStore } from '../theme'

describe('ThemeStore', () => {
  beforeEach(() => {
    // Reset store state to initial values
    useThemeStore.setState({ theme: 'light', resolvedTheme: 'light' })
    localStorage.clear()
    // Reset document class
    document.documentElement.classList.remove('dark')
  })

  it('should have initial theme as light', () => {
    const state = useThemeStore.getState()
    expect(state.theme).toBe('light')
  })

  it('should have initial resolvedTheme as light', () => {
    const state = useThemeStore.getState()
    expect(state.resolvedTheme).toBe('light')
  })

  it('should set theme to dark', () => {
    const { setTheme } = useThemeStore.getState()
    setTheme('dark')
    expect(useThemeStore.getState().theme).toBe('dark')
    expect(useThemeStore.getState().resolvedTheme).toBe('dark')
  })

  it('should set theme to light', () => {
    const { setTheme } = useThemeStore.getState()
    setTheme('dark')
    setTheme('light')
    expect(useThemeStore.getState().theme).toBe('light')
    expect(useThemeStore.getState().resolvedTheme).toBe('light')
  })

  it('should set theme to system', () => {
    const { setTheme } = useThemeStore.getState()
    setTheme('system')
    expect(useThemeStore.getState().theme).toBe('system')
  })

  it('should persist theme to localStorage with key tam-theme', () => {
    const { setTheme } = useThemeStore.getState()
    setTheme('dark')
    expect(localStorage.getItem('tam-theme')).toBe('dark')
  })

  it('should add dark class to document when theme is dark', () => {
    const { setTheme } = useThemeStore.getState()
    setTheme('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('should remove dark class from document when theme is light', () => {
    const { setTheme } = useThemeStore.getState()
    setTheme('dark')
    setTheme('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })
})
