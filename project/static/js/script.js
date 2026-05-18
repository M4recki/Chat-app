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

    const loadingOverlay = document.getElementById("chatbot-loading-overlay");

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
            });

            if (!response.ok) {
                throw new Error(`Request failed with status ${response.status}`);
            }

            window.location.reload();
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
