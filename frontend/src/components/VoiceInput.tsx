import { useRef, useState } from 'react'

interface Props {
  onTranscript: (text: string) => void
  disabled?: boolean
}

type SR = {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: any) => void) | null
  onend: (() => void) | null
  onerror: ((event: any) => void) | null
  start: () => void
  stop: () => void
}

function getSR(): (new () => SR) | null {
  const w = window as unknown as Record<string, unknown>
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition) as (new () => SR) | null
}

export function VoiceInput({ onTranscript, disabled }: Props) {
  const SR = getSR()
  const supported = SR !== null
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState('')
  const [error, setError] = useState('')
  const recRef = useRef<SR | null>(null)

  const stop = () => {
    recRef.current?.stop()
    setListening(false)
    setInterim('')
  }

  const start = () => {
    if (!SR || disabled) return
    setError('')
    const rec = new SR()
    rec.lang = 'en-US'
    rec.continuous = false
    rec.interimResults = true
    rec.onresult = (event: any) => {
      let finalText = ''
      let interimText = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) finalText += result[0].transcript
        else interimText += result[0].transcript
      }
      if (finalText.trim()) onTranscript(finalText.trim())
      setInterim(interimText)
    }
    rec.onend = () => {
      setListening(false)
      setInterim('')
    }
    rec.onerror = (event: any) => {
      setListening(false)
      setInterim('')
      setError(
        event?.error === 'not-allowed'
          ? 'Microphone permission denied.'
          : 'Speech recognition failed — you can type instead.',
      )
    }
    recRef.current = rec
    rec.start()
    setListening(true)
  }

  if (!supported) {
    return (
      <span className="voice-unsupported" title="Use Chrome or Edge for voice input">
        Voice unavailable in this browser
      </span>
    )
  }

  return (
    <div className="voice">
      <button
        type="button"
        className={`mic-btn ${listening ? 'listening' : ''}`}
        onClick={() => (listening ? stop() : start())}
        disabled={disabled}
        title={listening ? 'Stop listening' : 'Ask by voice'}
      >
        {listening ? '◼' : '🎤'}
      </button>
      {listening && <span className="voice-interim">“{interim}”</span>}
      {error && <span className="voice-error">{error}</span>}
    </div>
  )
}
