// This file contains JavaScript code for handling chatbot interactions, dynamic textarea resizing, and conversation deletion with confirmation dialogs. It also includes error handling and markdown rendering for chatbot responses.

document.addEventListener("DOMContentLoaded", () => {
    const messageTextareas = document.querySelectorAll(".chat_textarea");
    const openDeleteConfirmation = document.getElementById("open-delete-confirmation");
    const confirmDeleteConversation = document.getElementById("confirm-delete-conversation");
    const deleteConfirmationDialog = document.getElementById("delete-confirmation");
    const closeDeleteConfirmation = document.getElementById("close-dialog");

    if (openDeleteConfirmation && deleteConfirmationDialog) {
        openDeleteConfirmation.addEventListener("click", () => {
            deleteConfirmationDialog.showModal();
        });
    }

    if (closeDeleteConfirmation && deleteConfirmationDialog) {
        closeDeleteConfirmation.addEventListener("click", () => {
            deleteConfirmationDialog.close();
        });
    }

    // Handle conversation deletion with confirmation dialog and error handling

    if (confirmDeleteConversation) {
        confirmDeleteConversation.addEventListener("click", async () => {
            try {
                const response = await fetch("/clear_chatbot_messages", {
                    method: "POST",
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    credentials: "same-origin",
                });

                if (!response.ok) {
                    throw new Error(`Request failed with status ${response.status}`);
                }

                window.location.href = "/chatbot";
            } catch (error) {
                console.error(error);
                alert("Could not delete the conversation. Please try again.");
            }
        });
    }

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
    const chatbotStatus = document.getElementById("chatbot-status");

    const clearChatbotStatus = () => {
        if (!chatbotStatus) {
            return;
        }

        chatbotStatus.className = "alert d-none mt-3";
        chatbotStatus.innerHTML = "";
    };

    // Show chatbot status messages (errors or info) in a consistent format

    const showChatbotStatus = (title, details, variant = "danger") => {
        if (!chatbotStatus) {
            return;
        }

        chatbotStatus.className = `alert alert-${variant} mt-3`;
        chatbotStatus.innerHTML = "";

        const heading = document.createElement("strong");
        heading.textContent = title || "Chatbot error";
        chatbotStatus.appendChild(heading);

        if (details) {
            const detailBlock = document.createElement("pre");
            detailBlock.className = "mb-0 mt-2 small text-wrap";
            detailBlock.textContent =
                typeof details === "string" ? details : JSON.stringify(details, null, 2);
            chatbotStatus.appendChild(detailBlock);
        }
    };

    const normalizeChatbotMarkdown = (sourceText) => {
        const text = (sourceText || "").replace(/\r\n/g, "\n");
        const lines = text.split("\n");

        while (lines.length && !lines[0].trim()) {
            lines.shift();
        }

        while (lines.length && !lines[lines.length - 1].trim()) {
            lines.pop();
        }

        const indents = lines
            .filter((line) => line.trim())
            .map((line) => line.match(/^\s*/)?.[0].length || 0);

        const minIndent = indents.length ? Math.min(...indents) : 0;

        return lines.map((line) => line.slice(minIndent)).join("\n").trim();
    };

    // Render chatbot responses that may contain markdown, ensuring any existing content is processed on page load

    const renderChatbotMarkdown = (element, sourceText) => {
        if (!element) {
            return;
        }

        let htmlContent = normalizeChatbotMarkdown(sourceText);

        try {
            if (typeof marked !== "undefined" && typeof marked.parse === "function") {
                htmlContent = marked.parse(htmlContent);
            } else if (typeof marked !== "undefined" && typeof marked === "function") {
                htmlContent = marked(htmlContent);
            }

            if (typeof DOMPurify !== "undefined") {
                htmlContent = DOMPurify.sanitize(htmlContent);
            } else {
                console.warn("DOMPurify not loaded — markdown rendered without sanitization");
            }
        } catch (error) {
            console.error("Markdown parsing error:", error);
        }

        element.innerHTML = htmlContent;
        element.dataset.chatbotRendered = "true";
    };

    // On page load, find any existing chatbot responses and render their markdown content properly

    const hydrateExistingChatbotResponses = () => {
        document.querySelectorAll("[data-chatbot-response]").forEach((element) => {
            if (element.dataset.chatbotRendered === "true") {
                return;
            }

            renderChatbotMarkdown(element, element.textContent || "");
        });
    };

    hydrateExistingChatbotResponses();

    const formatLocalTimestamp = (date) => {
        const hours = date.getHours().toString().padStart(2, "0");
        const minutes = date.getMinutes().toString().padStart(2, "0");
        const day = date.getDate().toString().padStart(2, "0");
        const month = (date.getMonth() + 1).toString().padStart(2, "0");
        const year = date.getFullYear();
        return ` ${hours}:${minutes}, ${year}-${month}-${day}`;
    };

    const buildChatbotCard = (payload, options = {}) => {
        if (!chatbotThread) {
            return null;
        }

        const userName = chatbotThread.dataset.userName || "You";
        const userImage = chatbotThread.dataset.userImage || "";

        const card = document.createElement("div");
        card.className = "card mt-3";

        const cardBody = document.createElement("div");
        cardBody.className = "card-body";

        const title = document.createElement("p");
        title.className = "card-title";
        title.textContent = payload.created_at || formatLocalTimestamp(new Date());

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

        const botContainer = document.createElement("div");
        botContainer.className = "mt-3 text-start";

        const botStrong = document.createElement("strong");
        botStrong.className = "text-primary";

        const botIcon = document.createElement("i");
        botIcon.className = "bi bi-robot";
        botStrong.appendChild(botIcon);
        botStrong.appendChild(document.createTextNode(" Chatbot: "));

        botContainer.appendChild(botStrong);

        const botMessage = document.createElement("div");
        botMessage.className = "mt-2 chatbot-response-content";
        botMessage.dataset.chatbotResponse = "true";

        if (options.pending) {
            botMessage.textContent = "Chatbot is thinking...";
        } else if (payload.response) {
            renderChatbotMarkdown(botMessage, payload.response);
        }

        botContainer.appendChild(botMessage);
        cardBody.appendChild(botContainer);

        card.appendChild(cardBody);

        return {
            card,
            title,
            botMessage,
        };
    };

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

        clearChatbotStatus();

        const built = buildChatbotCard(payload, { pending: false });
        if (!built) {
            return false;
        }

        chatbotThread.insertBefore(built.card, formCard);
        return true;
    };

    chatbotForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        clearChatbotStatus();

        if (loadingOverlay) {
            loadingOverlay.classList.add("is-visible");
        }

        const submitButton = chatbotForm.querySelector("button[type='submit']");
        if (submitButton) {
            submitButton.disabled = true;
        }

        const formData = new FormData(chatbotForm);
        const messageValue = (formData.get("message") || "").toString();
        const pendingCard = buildChatbotCard(
            { message: messageValue, created_at: formatLocalTimestamp(new Date()) },
            { pending: true },
        );

        if (pendingCard && chatbotThread) {
            if (emptyState) {
                emptyState.remove();
            }
            const formCard = chatbotForm.closest(".card");
            if (formCard) {
                chatbotThread.insertBefore(pendingCard.card, formCard);
            }
        }

        try {
            const response = await fetch(chatbotForm.action, {
                method: chatbotForm.method,
                body: formData,
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
                credentials: "same-origin",
            });

            if (!response.ok) {
                const contentType = response.headers.get("content-type") || "";
                let errorPayload = {
                    message: `Request failed with status ${response.status}`,
                    details: { status: response.status },
                };

                if (contentType.includes("application/json")) {
                    try {
                        errorPayload = await response.json();
                    } catch (jsonError) {
                        console.error("Failed to parse chatbot error JSON:", jsonError);
                    }
                } else {
                    const errorText = await response.text();
                    if (errorText) {
                        errorPayload.details = errorText;
                    }
                }

                const error = new Error(errorPayload.message || "Could not send the message");
                error.payload = errorPayload;
                throw error;
            }

            const contentType = response.headers.get("content-type") || "";
            if (contentType.includes("application/json")) {
                const payload = await response.json();
                if (pendingCard) {
                    pendingCard.title.textContent = payload.created_at || pendingCard.title.textContent;
                    if (payload.response) {
                        renderChatbotMarkdown(pendingCard.botMessage, payload.response);
                    } else {
                        pendingCard.botMessage.textContent = "Chatbot returned an empty response.";
                    }
                } else if (!appendChatbotMessage(payload)) {
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

            const payload = error && error.payload ? error.payload : null;
            const title =
                payload?.message ||
                payload?.details?.message ||
                error.message ||
                "Could not send the message. Please try again.";
            const details =
                payload?.details || payload?.error_type || payload?.message || error.message;
            showChatbotStatus(title, details);

            if (pendingCard) {
                pendingCard.botMessage.textContent = "Chatbot failed to respond. Please try again.";
            }
            console.error(error);
        }
    });
});

function DeleteConfirmationClose(dialogId) {
    const id = dialogId || "delete-confirmation";
    const dialog = document.getElementById(id);
    if (dialog) {
        dialog.close();
    }
}
