'use client'

interface NumberInputWithUnitProps {
  label: string
  value: number | null
  unit: string
  min?: number
  max?: number
  placeholder?: string
  onChange: (value: number | null) => void
}

export function NumberInputWithUnit({
  label,
  value,
  unit,
  min,
  max,
  placeholder = '未填写',
  onChange,
}: NumberInputWithUnitProps) {
  return (
    <div className="flex items-center justify-between">
      <label className="text-sm font-medium text-foreground">{label}</label>
      <div className="flex items-center gap-2">
        <input
          type="number"
          value={value ?? ''}
          min={min}
          max={max}
          placeholder={placeholder}
          onChange={(e) => {
            const val = e.target.value
            onChange(val ? parseInt(val, 10) : null)
          }}
          className="w-20 px-3 py-2 rounded-xl bg-input border-2 border-border text-right focus:border-primary focus:ring-1 focus:ring-primary"
        />
        <span className="text-sm text-muted-foreground">{unit}</span>
      </div>
    </div>
  )
}