import { describe, it, expect } from 'vitest'
import { formatInr } from './formatInr'

describe('formatInr', () => {
  it('formats ₹1', () => {
    const result = formatInr(100)
    expect(result).toContain('1.00')
    expect(result).toContain('₹')
  })

  it('formats ₹100', () => {
    const result = formatInr(10000)
    expect(result).toContain('100.00')
  })

  it('formats ₹1,234', () => {
    const result = formatInr(123400)
    expect(result).toContain('1,234')
  })

  it('formats ₹12,34,567.89 (Indian grouping)', () => {
    const result = formatInr(123456789)
    // Indian grouping: 12,34,567.89
    expect(result).toContain('12,34,567.89')
  })

  it('formats zero', () => {
    const result = formatInr(0)
    expect(result).toContain('0.00')
  })
})
