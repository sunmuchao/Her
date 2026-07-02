'use client'

import { useState, useRef, useEffect } from 'react'
import { Search, MapPin, X } from 'lucide-react'
import { cn } from '@/lib/utils'

const POPULAR_CITIES = [
  '北京', '上海', '广州', '深圳', '杭州', '成都', 
  '南京', '武汉', '西安', '苏州', '重庆', '天津'
]

const ALL_CITIES = [
  // 直辖市
  '北京', '上海', '天津', '重庆',
  // 省会城市 & 主要城市
  '广州', '深圳', '杭州', '成都', '南京', '武汉', '西安', '苏州',
  '东莞', '佛山', '宁波', '郑州', '长沙', '青岛', '沈阳', '大连',
  '厦门', '福州', '济南', '哈尔滨', '长春', '昆明', '贵阳', '南宁',
  '太原', '石家庄', '合肥', '南昌', '兰州', '乌鲁木齐', '呼和浩特',
  '海口', '三亚', '珠海', '中山', '惠州', '无锡', '常州', '温州',
  '金华', '嘉兴', '绍兴', '台州', '烟台', '潍坊', '临沂', '徐州',
  '扬州', '泰州', '镇江', '盐城', '淮安', '连云港', '南通', '芜湖',
  '洛阳', '开封', '新乡', '焦作', '许昌', '漯河', '周口', '信阳',
  // 海外
  '香港', '澳门', '台北', '新加坡', '东京', '首尔', '纽约', '伦敦',
  '洛杉矶', '旧金山', '温哥华', '多伦多', '悉尼', '墨尔本'
]

interface CitySelectorProps {
  value: string | null
  onChange: (city: string) => void
  placeholder?: string
}

export function CitySelector({ value, onChange, placeholder = '选择城市' }: CitySelectorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const filteredCities = search 
    ? ALL_CITIES.filter(city => city.includes(search))
    : []

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isOpen])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSelect = (city: string) => {
    onChange(city)
    setIsOpen(false)
    setSearch('')
  }

  const handleClear = () => {
    onChange('')
    setSearch('')
  }

  if (!isOpen) {
    return (
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className={cn(
          'w-full px-4 py-3.5 rounded-xl text-base text-left transition-all bg-input border-2 border-border',
          'hover:border-primary/30 focus:border-primary focus:ring-1 focus:ring-primary focus-ring',
          value ? 'text-foreground' : 'text-muted-foreground'
        )}
      >
        <span className="flex items-center gap-2">
          <MapPin className="w-4 h-4 text-muted-foreground" />
          {value || placeholder}
        </span>
      </button>
    )
  }

  return (
    <div ref={containerRef} className="relative">
      {/* Search input */}
      <div className="relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          ref={inputRef}
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索城市..."
          className="w-full pl-10 pr-10 py-3.5 rounded-xl text-base outline-none transition-all bg-input border-2 border-primary ring-1 ring-primary text-foreground placeholder:text-muted-foreground"
        />
        {(search || value) && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-full hover:bg-secondary transition-colors"
          >
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        )}
      </div>

      {/* Dropdown */}
      <div className="absolute z-50 w-full mt-2 bg-card border border-border rounded-xl shadow-lg max-h-72 overflow-y-auto animate-scale-in">
        {/* Search results or popular cities */}
        {search ? (
          filteredCities.length > 0 ? (
            <div className="p-2">
              {filteredCities.map((city) => (
                <button
                  key={city}
                  type="button"
                  onClick={() => handleSelect(city)}
                  className={cn(
                    'w-full px-3 py-2.5 rounded-lg text-left text-sm transition-colors',
                    value === city 
                      ? 'bg-primary/10 text-primary font-medium' 
                      : 'hover:bg-secondary text-foreground'
                  )}
                >
                  {city}
                </button>
              ))}
            </div>
          ) : (
            <div className="p-4 text-center text-sm text-muted-foreground">
              没有找到"{search}"
              <button
                type="button"
                onClick={() => handleSelect(search)}
                className="block w-full mt-2 px-3 py-2 rounded-lg bg-secondary text-foreground text-sm hover:bg-secondary/80 transition-colors"
              >
                使用 "{search}"
              </button>
            </div>
          )
        ) : (
          <div className="p-3">
            <p className="text-xs text-muted-foreground mb-2 px-1">热门城市</p>
            <div className="flex flex-wrap gap-2">
              {POPULAR_CITIES.map((city) => (
                <button
                  key={city}
                  type="button"
                  onClick={() => handleSelect(city)}
                  className={cn(
                    'px-3 py-1.5 rounded-lg text-sm transition-all border',
                    value === city 
                      ? 'bg-primary text-primary-foreground border-primary' 
                      : 'bg-secondary/50 border-border text-foreground hover:border-primary/30'
                  )}
                >
                  {city}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
