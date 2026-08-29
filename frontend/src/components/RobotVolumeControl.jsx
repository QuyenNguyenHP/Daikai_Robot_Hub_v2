import * as React from 'react'
import { styled } from '@mui/material/styles'
import Box from '@mui/material/Box'
import Grid from '@mui/material/Grid'
import IconButton from '@mui/material/IconButton'
import MuiInput from '@mui/material/Input'
import Popover from '@mui/material/Popover'
import Slider from '@mui/material/Slider'
import Typography from '@mui/material/Typography'
import VolumeUp from '@mui/icons-material/VolumeUp'


const Input = styled(MuiInput)`
  width: 42px;
`

const clampVolume = (value) => Math.max(0, Math.min(100, value))

export default function RobotVolumeControl({
  busy,
  disabled,
  onApply,
  onChange,
  value,
}) {
  const [anchorElement, setAnchorElement] = React.useState(null)
  const labelId = React.useId()
  const open = Boolean(anchorElement)

  const handleSliderChange = (_event, newValue) => {
    onChange(Number(newValue))
  }

  const handleInputChange = (event) => {
    const nextValue = event.target.value === '' ? 0 : Number(event.target.value)
    if (Number.isFinite(nextValue)) onChange(clampVolume(nextValue))
  }

  const handleBlur = () => {
    onChange(clampVolume(Number(value)))
  }

  return (
    <>
      <IconButton
        type="button"
        className="robot-volume-trigger"
        aria-label={`Robot volume: ${value} percent`}
        aria-describedby={open ? labelId : undefined}
        disabled={disabled}
        onClick={(event) => setAnchorElement(event.currentTarget)}
      >
        <VolumeUp />
      </IconButton>
      <Popover
        open={open}
        anchorEl={anchorElement}
        onClose={() => setAnchorElement(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { className: 'robot-volume-popover' } }}
      >
        <Box sx={{ width: 280, p: 2 }}>
          <Typography id={labelId} gutterBottom>
            Robot volume
          </Typography>
          <Grid container spacing={2} sx={{ alignItems: 'center' }}>
            <Grid>
              <VolumeUp className="robot-volume-icon" />
            </Grid>
            <Grid size="grow">
              <Slider
                value={typeof value === 'number' ? value : 0}
                min={0}
                max={100}
                step={1}
                disabled={busy}
                onChange={handleSliderChange}
                aria-labelledby={labelId}
                valueLabelDisplay="auto"
              />
            </Grid>
            <Grid>
              <Input
                value={value}
                size="small"
                disabled={busy}
                onChange={handleInputChange}
                onBlur={handleBlur}
                inputProps={{
                  step: 1,
                  min: 0,
                  max: 100,
                  type: 'number',
                  'aria-labelledby': labelId,
                }}
              />
            </Grid>
          </Grid>
          <button
            type="button"
            className="button primary robot-volume-apply"
            disabled={busy}
            onClick={onApply}
          >
            {busy ? 'Setting…' : 'Set volume'}
          </button>
        </Box>
      </Popover>
    </>
  )
}
