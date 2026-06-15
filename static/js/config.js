export const CONFIG = {
  imgWidth: 520,
  jpegQuality: 0.48,
  intervals: {
    navigation: 1000,
    object_find: 250,
    precision: 250,
    task: 1000,
    ocr: 2200
  }
};

export const STATE = {
  active: false,
  mode: "navigation",
  target: "",
  stream: null,
  ws: null,
  loop: null,
  wsRetries: 0,
  recording: false,
  mediaRecorder: null,
  audioChunks: [],
  heading: 0,
  keyPrompted: false
};
