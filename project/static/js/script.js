// Reject friend request


const button = document.getElementById("cancel-button-delete");
if (button) {
    button.addEventListener("click", DeleteConfirmationClose);
}


function DeleteConfirmationClose() {
    const dialog = document.getElementById("delete-confirmation");
    dialog.close();
}

// Chatbot form submission with loading overlay and error handling

document.addEventListener("DOMContentLoaded", () => {
    const messageTextareas = document.querySelectorAll(".chatbot-textarea");

    messageTextareas.forEach((textarea) => {
        const resizeTextarea = () => {
            textarea.style.height = "auto";
            const nextHeight = Math.min(textarea.scrollHeight, 224);
            textarea.style.height = `${nextHeight}px`;
        };

        resizeTextarea();
        textarea.addEventListener("input", resizeTextarea);

        textarea.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                const parentForm = textarea.closest("form");

                if (!parentForm) {
                    return;
                }

                if (parentForm.requestSubmit) {
                    parentForm.requestSubmit();
                } else {
                    parentForm.submit();
                }
            }
        });
    });

    const chatbotForm = document.querySelector("form[action='/chatbot']");
    if (!chatbotForm) {
        return;
    }

    // Cache references to elements used in the form submission handler

    const loadingOverlay = document.getElementById("chatbot-loading-overlay");
    const chatbotThread = document.querySelector("[data-chatbot-thread]");
    const emptyState = document.getElementById("chatbot-empty-state");

    const appendChatbotMessage = (payload) => {
        if (!chatbotThread) {
            return false;
        }

        const formCard = chatbotForm.closest(".card");
        if (!formCard) {
            return false;
        }

        if (emptyState) {
            emptyState.remove();
        }

        const userName = chatbotThread.dataset.userName || "You";
        const userImage = chatbotThread.dataset.userImage || "";

        const card = document.createElement("div");
        card.className = "card mt-3";

        const cardBody = document.createElement("div");
        cardBody.className = "card-body";

        const title = document.createElement("p");
        title.className = "card-title";
        title.textContent = ` ${payload.created_at || ""}`;

        const userMessage = document.createElement("p");
        userMessage.className = "py-3 text-start";

        const avatar = document.createElement("img");
        avatar.className = "smaller-user-image me-1";
        avatar.src = userImage;
        avatar.alt = `${userName}'s avatar`;

        const userStrong = document.createElement("strong");
        userStrong.className = "text-primary";
        userStrong.textContent = `${userName}: `;

        userMessage.appendChild(avatar);
        userMessage.appendChild(userStrong);
        userMessage.appendChild(document.createTextNode(payload.message || ""));

        cardBody.appendChild(title);
        cardBody.appendChild(userMessage);

        if (payload.response) {
            const botMessage = document.createElement("p");
            botMessage.className = "mt-3 text-start";

            const botStrong = document.createElement("strong");
            botStrong.className = "text-primary";

            const botIcon = document.createElement("i");
            botIcon.className = "bi bi-robot";
            botStrong.appendChild(botIcon);
            botStrong.appendChild(document.createTextNode(" Chatbot: "));

            botMessage.appendChild(botStrong);
            botMessage.appendChild(document.createTextNode(payload.response));
            cardBody.appendChild(botMessage);
        }

        card.appendChild(cardBody);
        chatbotThread.insertBefore(card, formCard);
        return true;
    };

    chatbotForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        if (loadingOverlay) {
            loadingOverlay.classList.add("is-visible");
        }

        const submitButton = chatbotForm.querySelector("button[type='submit']");
        if (submitButton) {
            submitButton.disabled = true;
        }

        try {
            const response = await fetch(chatbotForm.action, {
                method: chatbotForm.method,
                body: new FormData(chatbotForm),
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
                // ensure cookies (access_token) are sent with the AJAX request
                credentials: 'same-origin',
            });

            if (!response.ok) {
                throw new Error(`Request failed with status ${response.status}`);
            }

            const contentType = response.headers.get("content-type") || "";
            if (contentType.includes("application/json")) {
                const payload = await response.json();
                if (!appendChatbotMessage(payload)) {
                    window.location.reload();
                }
            } else {
                window.location.reload();
            }

            chatbotForm.reset();
            messageTextareas.forEach((textarea) => {
                textarea.style.height = "auto";
            });
            if (loadingOverlay) {
                loadingOverlay.classList.remove("is-visible");
            }
            if (submitButton) {
                submitButton.disabled = false;
            }
        } catch (error) {
            if (loadingOverlay) {
                loadingOverlay.classList.remove("is-visible");
            }

            if (submitButton) {
                submitButton.disabled = false;
            }

            console.error(error);
            alert("Could not send the message. Please try again.");
        }
    });
});
