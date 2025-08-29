#! /bin/bash

create_env() {
    echo "creating .env file..."
    if [ ! -f "$BACKUP_FILE" ]; then
        # First time setup - use env.example
        cp env.example ".env"
    fi

    # Function to get existing value from .env
    get_existing_value() {
        local key=$1
        local value=$(grep "^$key=" .env | cut -d'=' -f2-)
        # If no existing value, get the placeholder from env.example
        if [ -z "$value" ]; then
            value=$(grep "^$key=" env.example | cut -d'=' -f2-)
        fi
        # Don't return placeholder values like <telegram-chat-id>
        if [[ "$value" =~ ^\<.*\>$ ]]; then
            echo ""
        else
            echo "$value"
        fi
    }

    # Function to prompt user with existing value
    prompt_with_existing() {
        local prompt=$1
        local key=$2
        local existing_value=$(get_existing_value "$key")

        if [ ! -f "$BACKUP_FILE" ]; then
            # First time setup - show simple prompt
            echo "🫸 ▶︎ $prompt: "
        else
            # Updating existing values - show current value
            if [ "$key" == "SIGNER_ACCOUNT_PRIVATE_KEY" ]; then
                echo "🫸 ▶︎ $prompt (press enter to keep current value: [hidden]): "
            elif [ -z "$existing_value" ]; then
                # No existing value - just show the prompt
                echo "🫸 ▶︎ $prompt: "
            else
                echo "🫸 ▶︎ $prompt (press enter to keep current value: $existing_value): "
            fi
        fi
    }

    # Function to update env value
    update_env_value() {
        local key=$1
        local value=$2

        # Check if key exists in the file
        if grep -q "^$key=" .env; then
            # Key exists, update it
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|^$key=.*|$key=$value|g" .env
            else
                sed -i "s|^$key=.*|$key=$value|g" .env
            fi
        else
            # Key doesn't exist, append it with proper newline
            # Check if file ends with newline
            if [ -n "$(tail -c 1 .env 2>/dev/null)" ]; then
                # File doesn't end with newline, add one
                echo "" >> .env
            fi
            echo "$key=$value" >> .env
        fi
    }

    # WALLET_HOLDER_ADDRESS
    prompt_with_existing "Please enter the WALLET_HOLDER_ADDRESS" "WALLET_HOLDER_ADDRESS"
    read input
    [ -n "$input" ] && update_env_value "WALLET_HOLDER_ADDRESS" "$input"

    # SOURCE_RPC_URL
    prompt_with_existing "Please enter the SOURCE_RPC_URL" "SOURCE_RPC_URL"
    read input
    [ -n "$input" ] && update_env_value "SOURCE_RPC_URL" "$input"

    # SIGNER_ACCOUNT_ADDRESS
    prompt_with_existing "Please enter the SIGNER_ACCOUNT_ADDRESS" "SIGNER_ACCOUNT_ADDRESS"
    read input
    [ -n "$input" ] && update_env_value "SIGNER_ACCOUNT_ADDRESS" "$input"

    # SIGNER_ACCOUNT_PRIVATE_KEY
    prompt_with_existing "Please enter the SIGNER_ACCOUNT_PRIVATE_KEY" "SIGNER_ACCOUNT_PRIVATE_KEY"
    read -s input
    echo "" # add a newline after hidden input
    [ -n "$input" ] && update_env_value "SIGNER_ACCOUNT_PRIVATE_KEY" "$input"

    # TELEGRAM_CHAT_ID
    prompt_with_existing "Please enter the TELEGRAM_CHAT_ID (press enter to skip)" "TELEGRAM_CHAT_ID"
    read input

    # Get existing TELEGRAM_CHAT_ID value
    existing_chat_id=$(get_existing_value "TELEGRAM_CHAT_ID")

    # Determine final chat ID value
    if [ -n "$input" ]; then
        # User entered a new value
        final_chat_id="$input"
        update_env_value "TELEGRAM_CHAT_ID" "$input"
    elif [ -z "$input" ] && [ -n "$existing_chat_id" ]; then
        # User pressed enter and there's an existing value - keep it
        final_chat_id="$existing_chat_id"
    else
        # User pressed enter and there's no existing value - clear it
        final_chat_id=""
        update_env_value "TELEGRAM_CHAT_ID" ""
        update_env_value "TELEGRAM_MESSAGE_THREAD_ID" ""
    fi

    # Only ask for thread ID if we have a chat ID
    if [ -n "$final_chat_id" ]; then
        # TELEGRAM_MESSAGE_THREAD_ID (only ask if TELEGRAM_CHAT_ID is provided)
        prompt_with_existing "Please enter the TELEGRAM_MESSAGE_THREAD_ID for organizing notifications (press enter to skip)" "TELEGRAM_MESSAGE_THREAD_ID"
        read thread_input

        # Get existing TELEGRAM_MESSAGE_THREAD_ID value
        existing_thread_id=$(get_existing_value "TELEGRAM_MESSAGE_THREAD_ID")

        # Handle thread ID input
        if [ -n "$thread_input" ]; then
            # User entered a new value
            update_env_value "TELEGRAM_MESSAGE_THREAD_ID" "$thread_input"
        elif [ -z "$thread_input" ] && [ -z "$existing_thread_id" ]; then
            # User pressed enter and there's no existing value - clear it
            update_env_value "TELEGRAM_MESSAGE_THREAD_ID" ""
        fi
        # If user pressed enter and there's an existing value, keep it (do nothing)
    fi

    echo "🟢 .env file created successfully!"
}

# Main script flow
if [ ! -f ".env" ]; then
    echo "🟡 .env file not found, please follow the instructions below to create one!"
    BACKUP_FILE=""  # Set empty backup file when no .env exists
    create_env
else
    echo "🟢 .env file already found to be initialized! If you wish to change any of the values, please backup the .env file at the following prompt."
    TIMESTAMP=$(date +%Y%m%d%H%M%S)
    BACKUP_FILE=".env.backup.${TIMESTAMP}"
    echo "Do you wish to backup and modify the .env file? (y/n)"
    read BACKUP_CHOICE
    if [ "$BACKUP_CHOICE" == "y" ]; then
        cp .env "$BACKUP_FILE"  # Changed from mv to cp to preserve original
        echo "🟢 .env file backed up to $BACKUP_FILE"
        create_env
    fi
fi
