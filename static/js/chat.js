// polling-based chat UI helper (no socket.io needed)
window.chatState = { contactId: null, contactName: null, pollTimer: null, myId: null };

function startChat(contactId, contactName) {
  window.chatState.contactId = contactId;
  window.chatState.contactName = contactName;

  const root = document.getElementById('chat-root');
  root.innerHTML = `
    <div class="chat">
      <header class="chat-header"><strong>${contactName}</strong></header>
      <div id="messages" class="messages"></div>
      <form id="sendForm">
        <textarea id="messageText" placeholder="Type a message..." required></textarea>
        <select id="selfDestruct">
          <option value="">No self-destruct</option>
          <option value="10s">10s</option>
          <option value="1m">1m</option>
          <option value="5m">5m</option>
        </select>
        <button type="submit">Send</button>
      </form>
    </div>
  `;

  document.getElementById('sendForm').addEventListener('submit', function (e) {
    e.preventDefault();
    sendMessage();
  });

  loadMessages();
  if (window.chatState.pollTimer) clearInterval(window.chatState.pollTimer);
  window.chatState.pollTimer = setInterval(loadMessages, 4000);
}

async function getMyId() {
  if (window.chatState.myId) return window.chatState.myId;
  const resp = await fetch('/api/whoami');
  if (resp.ok) {
    const data = await resp.json();
    window.chatState.myId = data.id;
  }
  return window.chatState.myId;
}

let lastMessageCount = 0;

function loadMessages() {
  if (!window.chatState.contactId) return;

  fetch(`/messages/${window.chatState.contactId}`)
    .then((r) => r.json())
    .then((data) => {
      const container = document.getElementById("messages");
      if (!container) return;

      // 🚀 Only re-render if number of messages changed
      if (data.length === lastMessageCount) return;
      lastMessageCount = data.length;

      container.innerHTML = "";

      data.forEach((m) => {
        const div = document.createElement("div");
        const isMe = m.from === window.currentUserId;
        div.className = "message " + (isMe ? "me" : "them");

        if (m.is_image && m.file_url) {
  const img = document.createElement('img');
  img.src = m.file_url;
  img.alt = 'Hidden message image';
  img.title = '🖼️ Click to view • 🕵️ Double-click to reveal hidden message';
  img.style.maxWidth = '220px';
  img.style.borderRadius = '10px';
  img.style.cursor = 'pointer';
  img.style.transition = 'transform 0.2s ease, box-shadow 0.2s ease';

  // Hover glow
  img.addEventListener('mouseenter', () => {
    img.style.transform = 'scale(1.05)';
    img.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.3)';
  });
  img.addEventListener('mouseleave', () => {
    img.style.transform = 'scale(1)';
    img.style.boxShadow = 'none';
  });

  // 🖼️ SINGLE CLICK → open image preview modal
let clickTimer = null;

img.addEventListener('click', () => {
  if (clickTimer) clearTimeout(clickTimer);
  clickTimer = setTimeout(() => {
    // 🖼️ SINGLE CLICK → show image preview modal
    const modal = document.getElementById('imagePreviewModal');
    const preview = document.getElementById('previewImage');
    preview.src = m.file_url;
    modal.style.display = 'flex';

    modal.onclick = (e) => {
      if (e.target === modal) modal.style.display = 'none';
    };
  }, 250); // wait a bit to see if user double-clicks
});

img.addEventListener('dblclick', async (event) => {
  if (clickTimer) clearTimeout(clickTimer); // cancel single-click
  event.stopPropagation();

  try {
    const res = await fetch('/extract_stego_by_filename', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: m.file_url.split('/').pop() })
    });

    const json = await res.json();
    const modal = document.getElementById('hiddenMessageModal');
    const messageBox = document.getElementById('hiddenMessageText');
    const closeBtn = document.getElementById('closeModalBtn');

    if (json.status === 'ok' && json.message) {
      messageBox.textContent = json.message;
    } else if (json.status === 'ok' && !json.message) {
      messageBox.textContent = 'No hidden message found in this image.';
    } else {
      messageBox.textContent = 'Extraction failed: ' + (json.message || 'unknown error');
    }

    modal.style.display = 'flex';
    closeBtn.onclick = () => (modal.style.display = 'none');
    modal.onclick = (e) => {
      if (e.target === modal) modal.style.display = 'none';
    };
  } catch (err) {
    console.error('extract error', err);
    const modal = document.getElementById('hiddenMessageModal');
    const messageBox = document.getElementById('hiddenMessageText');
    messageBox.textContent = '⚠️ Network or server error while extracting.';
    modal.style.display = 'flex';
  }
});

div.appendChild(img);

        }




         else if (m.text && m.text !== "[Decryption failed]") {
          div.textContent = m.text;
        } else {
          div.textContent = "[Decryption failed]";
          div.style.color = "#dc2626";
        }

        if (m.self_destruct_at) {
          const expiry = new Date(m.self_destruct_at);
          const infoDiv = document.createElement("div");
          infoDiv.className = "self-destruct-info";

          const disclaimer = document.createElement("small");
          disclaimer.textContent = "⚠️ Self-destructs soon";
          infoDiv.appendChild(disclaimer);

          const countdown = document.createElement("span");
          countdown.className = "countdown";
          countdown.style.marginLeft = "4px";
          infoDiv.appendChild(countdown);

          function updateCountdown() {
  const diff = Math.floor((expiry - new Date()) / 1000);
  if (diff > 0) {
    const mins = Math.floor(diff / 60);
    const secs = diff % 60;
    countdown.textContent = `⏱ ${mins}:${secs.toString().padStart(2, "0")} remaining`;
  } else {
    // 🔥 Instantly remove from DOM when timer ends
    div.classList.add("fade-out");
    countdown.textContent = "💥 Destroyed";
    setTimeout(() => div.remove(), 400); // instant fade-out
    clearInterval(interval);
  }
}

          updateCountdown();
          const interval = setInterval(updateCountdown, 1000);
          div.appendChild(infoDiv);
        }

        container.appendChild(div);
      });

      container.scrollTop = container.scrollHeight;
    })
    .catch((err) => console.error("Load messages error:", err));
}



function sendMessage() {
  const textBox = document.getElementById('messageText');
  const text = textBox.value.trim();
  const sd = document.getElementById('selfDestruct').value;

  if (!text) return;

  // ✅ build correct form data
  const formData = new FormData();
  formData.append("receiver_id", window.chatState.contactId);
  formData.append("text", text);  // must match Flask
  formData.append("self_destruct", sd);

  // ✅ add message immediately in chat UI
  const container = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'message me';
  div.textContent = text;

  // self-destruct timer UI
  if (sd) {
    const info = document.createElement('div');
    info.className = 'self-destruct-info';
    info.innerHTML = `⚠️ This message will self-destruct in <span class="countdown"></span>`;
    div.appendChild(info);

    let remaining = sd === '10s' ? 10 : sd === '1m' ? 60 : 300;
    const countdownEl = info.querySelector('.countdown');
    const interval = setInterval(() => {
      if (remaining > 0) {
        const mins = Math.floor(remaining / 60);
        const secs = remaining % 60;
        countdownEl.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
        remaining--;
      } else {
        div.classList.add('fade-out');
        setTimeout(() => div.remove(), 1000);
        clearInterval(interval);
      }
    }, 1000);
  }

  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  textBox.value = '';

  // ✅ send to Flask backend
  fetch('/send_message', { method: 'POST', body: formData })
    .then(r => r.json())
    .then(res => {
      if (!res.success) {
        alert('Send failed: ' + (res.message || 'Unknown error'));
        div.remove();
      } else {
        console.log('✅ Message sent successfully:', res);
        loadMessages(); // refresh chat panel
      }
    })
    .catch(err => {
      console.error('Send message error:', err);
      alert('Network error — try again.');
      div.remove();
    });
}
