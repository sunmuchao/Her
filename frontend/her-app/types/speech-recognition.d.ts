// Web Speech API type definitions
interface SpeechRecognitionErrorEvent extends Event {
  error: string
  message?: string
}

interface SpeechRecognitionEvent extends Event {
  resultIndex: number
  results: SpeechRecognitionResultList
}

interface SpeechRecognitionResultList {
  readonly length: number
  item(index: number): SpeechRecognitionResult
  [index: number]: SpeechRecognitionResult
}

interface SpeechRecognitionResult {
  readonly length: number
  readonly isFinal: boolean
  item(index: number): SpeechRecognitionAlternative
  [index: number]: SpeechRecognitionAlternative
}

interface SpeechRecognitionAlternative {
  readonly transcript: string
  readonly confidence: number
}

interface SpeechRecognition extends EventTarget {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  grammars: SpeechGrammarList

  start(): void
  stop(): void
  abort(): void

  onresult: ((event: SpeechRecognitionEvent) => void) | null
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null
  onend: (() => void) | null
  onstart: (() => void) | null
  onspeechend: (() => void) | null
  onnomatch: (() => void) | null
  onaudiostart: (() => void) | null
  onaudioend: (() => void) | null
  onsoundstart: (() => void) | null
  onsoundend: (() => void) | null
  onspeechstart: (() => void) | null
}

interface SpeechGrammarList {
  readonly length: number
  item(index: number): SpeechGrammar
  addFromString(string: string, weight?: number): void
  addFromURI(src: string, weight?: number): void
  [index: number]: SpeechGrammar
}

interface SpeechGrammar {
  src: string
  weight: number
}

declare let SpeechRecognition: {
  prototype: SpeechRecognition
  new (): SpeechRecognition
}

declare let webkitSpeechRecognition: {
  prototype: SpeechRecognition
  new (): SpeechRecognition
}

interface Window {
  SpeechRecognition: typeof SpeechRecognition
  webkitSpeechRecognition: typeof SpeechRecognition
}
