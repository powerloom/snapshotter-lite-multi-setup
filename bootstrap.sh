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
        echo "$value"
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
            else
                echo "🫸 ▶︎ $prompt (press enter to keep current value: $existing_value): "
            fi
        fi
    }

    # Function to update env value
    update_env_value() {
        local key=$1
        local value=$2
        local existing_value=$(get_existing_value "$key")

        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|^$key=.*|$key=$value|g" .env
        else
            sed -i "s|^$key=.*|$key=$value|g" .env
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
    if [ -z "$input" ]; then
        # If user pressed enter (skipped), explicitly set to blank
        update_env_value "TELEGRAM_CHAT_ID" ""
    elif [ -n "$input" ]; then
        # If user entered a value, use it
        update_env_value "TELEGRAM_CHAT_ID" "$input"
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
