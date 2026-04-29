"""multi_clone env generation wiring."""

from multi_clone import generate_env_file_contents


def test_generate_env_file_contents_forwards_telegram_tuning_kwargs():
    content = generate_env_file_contents(
        data_market_namespace="UNISWAPV2",
        source_rpc_url="http://eth",
        signer_addr="0x1",
        signer_pkey="0x2",
        powerloom_rpc_url="http://pl",
        data_market_contract="0x3",
        slot_id="5",
        snapshotter_config_repo="https://github.com/a/b.git",
        snapshotter_config_repo_branch="b1",
        snapshotter_compute_repo="https://github.com/c/d.git",
        snapshotter_compute_repo_branch="b2",
        telegram_chat_id="",
        telegram_reporting_url="",
        max_stream_pool_size=2,
        stream_pool_health_check_interval=30,
        local_collector_image_tag="latest",
        connection_refresh_interval_sec=60,
        telegram_notification_cooldown=99,
        telegram_missed_batch_size=7,
    )
    assert "TELEGRAM_NOTIFICATION_COOLDOWN=99\n" in content
    assert "TELEGRAM_MISSED_BATCH_SIZE=7\n" in content
