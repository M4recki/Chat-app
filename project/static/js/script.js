// Reject friend request

document.getElementById("cancel-button-delete").addEventListener("click", DeleteConfirmationClose)

function DeleteConfirmationClose() {
    var dialog = document.getElementById("delete-confirmation");
    dialog.close();
}