const config = window.DEMO_CONFIG || { apiBase: "", name: "Payer demo" };
const api = (config.apiBase || "").replace(/\/$/, "");
document.getElementById("demo-name").textContent = config.name || "Payer demo";

const prompts = [
  "How many members are in this demo?",
  "How many claims are denied?",
  "Which care programs have the most members?",
  "Find member Adler and summarize their claims",
];

const promptsEl = document.getElementById("prompts");
prompts.forEach((text) => {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = text;
  button.addEventListener("click", () => ask(text));
  promptsEl.appendChild(button);
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(tab.dataset.panel).classList.add("active");
  });
});

const thread = document.getElementById("thread");

function addBubble(text, role) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  bubble.textContent = text;
  thread.appendChild(bubble);
  thread.scrollTop = thread.scrollHeight;
}

async function post(path, message) {
  const response = await fetch(`${api}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "The demo agent could not answer");
  return body.answer;
}

async function ask(message) {
  document.querySelector('[data-panel="chat"]').click();
  addBubble(message, "user");
  addBubble("Looking in the demo database…", "agent");
  const pending = thread.lastChild;
  try {
    pending.textContent = await post("/chat", message);
  } catch (error) {
    pending.textContent = error.message;
    pending.classList.add("error");
  }
}

document.getElementById("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.getElementById("chat-input");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  ask(message);
});

const callButton = document.getElementById("call-button");
const callStatus = document.getElementById("call-status");
const callTranscript = document.getElementById("call-transcript");
let callLive = false;
let recognizer = null;
let synthesizer = null;

async function speechConfig() {
  const response = await fetch(`${api}/speech/token`, { method: "POST" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "Voice is not available");
  return SpeechSDK.SpeechConfig.fromAuthorizationToken(body.token, body.region);
}

async function startCall() {
  callLive = true;
  callButton.textContent = "End call";
  callButton.classList.add("live");
  callStatus.textContent = "Listening";
  const speech = await speechConfig();
  speech.speechRecognitionLanguage = "en-US";
  speech.speechSynthesisVoiceName = "en-US-JennyNeural";
  recognizer = new SpeechSDK.SpeechRecognizer(speech, SpeechSDK.AudioConfig.fromDefaultMicrophoneInput());
  synthesizer = new SpeechSDK.SpeechSynthesizer(speech);
  recognizer.recognized = async (_sender, event) => {
    if (!callLive || event.result.reason !== SpeechSDK.ResultReason.RecognizedSpeech) return;
    const heard = event.result.text.trim();
    if (!heard) return;
    callTranscript.textContent = `You: ${heard}`;
    callStatus.textContent = "Looking up the answer";
    try {
      const reply = await post("/voice", heard);
      callTranscript.textContent = `You: ${heard}\n\nAgent: ${reply}`;
      callStatus.textContent = "Speaking";
      recognizer.stopContinuousRecognitionAsync(() => {
        synthesizer.speakTextAsync(reply, () => {
          if (!callLive) return;
          recognizer.startContinuousRecognitionAsync();
          callStatus.textContent = "Listening";
        });
      });
    } catch (error) {
      callStatus.textContent = error.message;
    }
  };
  recognizer.startContinuousRecognitionAsync();
}

function endCall() {
  callLive = false;
  callButton.textContent = "Start call";
  callButton.classList.remove("live");
  callStatus.textContent = "Ready";
  if (recognizer) recognizer.stopContinuousRecognitionAsync();
  if (synthesizer) synthesizer.close();
  recognizer = null;
  synthesizer = null;
}

callButton.addEventListener("click", async () => {
  if (callLive) {
    endCall();
    return;
  }
  if (typeof SpeechSDK === "undefined") {
    callStatus.textContent = "The voice library did not load.";
    return;
  }
  try {
    await startCall();
  } catch (error) {
    endCall();
    callStatus.textContent = error.message;
  }
});
