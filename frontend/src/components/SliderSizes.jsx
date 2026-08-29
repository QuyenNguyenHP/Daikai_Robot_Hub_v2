import Box from '@mui/material/Box'
import Slider from '@mui/material/Slider'


export default function SliderSizes({
  ariaLabel,
  disabled = false,
  max,
  min,
  onChange,
  size = 'small',
  step,
  value,
}) {
  return (
    <Box sx={{ width: '100%' }}>
      <Slider
        size={size}
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        aria-label={ariaLabel}
        valueLabelDisplay="auto"
        onChange={(_event, nextValue) => onChange(nextValue)}
        sx={{
          color: 'var(--cyan)',
          '& .MuiSlider-valueLabel': {
            backgroundColor: '#16304a',
            color: '#eaf4ff',
          },
        }}
      />
    </Box>
  )
}
