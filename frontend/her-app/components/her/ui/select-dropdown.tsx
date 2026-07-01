'use client'

import { useState } from 'react'
import { ChevronDown } from 'lucide-react'

interface SelectDropdownProps {
  label: string
  value: string | null
  options: Array<{ value: string; label: string }>
  placeholder?: string
  onChange: (value: string | null) => void
}

export function SelectDropdown({
  label,
  value,
  options,
  placeholder = '未填写',
  onChange,
}: SelectDropdownProps) {
  const [isOpen, setIsOpen] = useState(false)

  const selectedOption = options.find((opt) => opt.value === value)

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-foreground">{label}</label>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-4 py-3.5 rounded-xl bg-input border-2 border-border text-left flex items-center justify-between hover:border-primary/30 transition-colors"
      >
        <span className={value ? 'text-foreground' : 'text-muted-foreground'}>
          {selectedOption?.label || placeholder}
        </span>
        <ChevronDown className="w-5 h-5 text-muted-foreground" />
      </button>

      {isOpen && (
        <div className="space-y-2 animate-scale-in">
          {options.map((option) => (
            <button
              key={option.value}
              onClick={() => {
                onChange(option.value)
                setIsOpen(false)
              }}
              className={
                option.value === value
                  ? 'w-full px-4 py-3 rounded-xl bg-primary text-primary-foreground border-2 border-primary'
                  : 'w-full px-4 py-3 rounded-xl bg-input border-2 border-border text-foreground hover:border-primary/30'
              }
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}