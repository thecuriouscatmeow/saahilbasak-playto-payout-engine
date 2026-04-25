import { formatInr } from '../utils/formatInr'

interface Props {
  paise: number
  tone?: 'default' | 'muted'
}

export function MoneyText({ paise, tone = 'default' }: Props) {
  return (
    <span className={tone === 'muted' ? 'text-gray-500' : 'text-gray-900 font-semibold'}>
      {formatInr(paise)}
    </span>
  )
}
