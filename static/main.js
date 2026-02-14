const myId = document.getElementById('mydata').dataset.myid;
let usersList = JSON.parse(document.getElementById('mydata').dataset.users);

const socket = io();
let currentRoom = null;
let currentReceiver = null;

const usersDiv = document.getElementById('users');
const chatBox = document.getElementById('chat-box');
const chatHeader = document.getElementById('chat-header');

function renderUsers(list) {
  usersDiv.innerHTML = '';
  list.forEach(u => {
    const div = document.createElement('div');
    div.classList.add('user');
    div.dataset.id = u.id;
    div.textContent = u.username;
    div.onclick = () => {
      currentReceiver = u.id;
      currentRoom = 'chat_' + Math.min(myId, currentReceiver) + '_' + Math.max(myId, currentReceiver);
      socket.emit('join', { room: currentRoom });
      chatHeader.textContent = `Chat with ${u.username}`;
      loadMessages(u.id);
    };
    usersDiv.appendChild(div);
  });
}

// Initial render
renderUsers(usersList);

// ---------------- Search Users ----------------
document.getElementById('search').addEventListener('input', e => {
  const filter = e.target.value.toLowerCase();
  const filtered = usersList.filter(u => u.username.toLowerCase().includes(filter));
  renderUsers(filtered);
});

// ---------------- Send Message ----------------
document.getElementById('send').onclick = () => {
  if (!currentReceiver) return;
  const message = document.getElementById('msg').value.trim();
  if (!message) return;
  socket.emit('send_message', { sender: myId, receiver: currentReceiver, message });
  document.getElementById('msg').value = '';
};

// ---------------- Receive Message ----------------
socket.on('receive_message', data => {
  if (!currentRoom) return;
  const expectedRoom = 'chat_' + Math.min(myId, data.receiver) + '_' + Math.max(myId, data.receiver);
  if (expectedRoom !== currentRoom) return;

  chatBox.innerHTML += `<div class="${data.sender == myId ? 'msg sent' : 'msg received'}"><b>${data.sender == myId ? 'You' : 'User'}</b>: ${data.message}</div>`;
  chatBox.scrollTop = chatBox.scrollHeight;
});

// ---------------- Load Past Messages ----------------
function loadMessages(otherId) {
  fetch(`/messages/${otherId}`)
    .then(res => res.json())
    .then(msgs => {
      chatBox.innerHTML = '';
      msgs.forEach(m => {
        chatBox.innerHTML += `<div class="${m.sender_id == myId ? 'msg sent' : 'msg received'}"><b>${m.sender_id == myId ? 'You' : 'User'}</b>: ${m.message}</div>`;
      });
      chatBox.scrollTop = chatBox.scrollHeight;
    });
}
