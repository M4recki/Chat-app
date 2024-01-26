// Reject friend request


document.getElementById("cancel-button-delete").addEventListener("click", DeleteConfirmationClose)

function DeleteConfirmationClose() {
    const dialog = document.getElementById("delete-confirmation");
    dialog.close();
}


// Websocket


const channel_id = "{{ channel_id }}";

const ws = new WebSocket(`ws://127.0.0.1:8000/friend_chat/${channel_id}`);
ws.onmessage = function (event) {

    const messages = document.getElementById("messages");
    const message = document.createElement("li");
    const content = document.createTextNode(
        event.data.message || event.data.data
    );

    message.appendChild(content);
    messages.appendChild(message);
};
console.log(channel_id)
function sendMessage(event) {
    const input = document.getElementById("messageText");
    ws.send(input.value);
    input.value = "";
    event.preventDefault();
}