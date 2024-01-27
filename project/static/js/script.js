// Reject friend request


const button = document.getElementById("cancel-button-delete");
if (button) {
    button.addEventListener("click", DeleteConfirmationClose);
}


function DeleteConfirmationClose() {
    const dialog = document.getElementById("delete-confirmation");
    dialog.close();
}

const channel_id = "";

const ws = new WebSocket(`ws://localhost:8000/ws/friend_chat/${channel_id}`);
            ws.onmessage = function(event) {
                const messages = document.getElementById('messages')
                const message = document.createElement('li')
                const content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
                console.log(message)
                console.log(messages)
            };
            function sendMessage(event) {
                const input = document.getElementById("messageText")
                ws.send(input.value)
                input.value = ''
                event.preventDefault()
                console.log(input.value)
            }
