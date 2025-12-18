from pathlib import Path
from typing import Dict, List, Optional, Set, Union

from pydantic import BaseModel, HttpUrl


class ChainConfig(BaseModel):
    name: str
    chainId: int
    rpcURL: HttpUrl


class ComputeConfig(BaseModel):
    repo: HttpUrl
    branch: str
    commit: Optional[str]


class MarketConfig(BaseModel):
    name: str
    contractAddress: str
    powerloomProtocolStateContractAddress: str
    sourceChain: str
    sequencer: str
    compute: ComputeConfig
    config: ComputeConfig
    bootstrapNodes: Optional[List[str]] = None  # List of bootstrap node multiaddrs


class PowerloomChainConfig(BaseModel):
    powerloomChain: ChainConfig
    dataMarkets: Optional[List[MarketConfig]]


class ChainMarketData:
    def __init__(self, chain_config: ChainConfig, markets: Dict[str, MarketConfig]):
        self.chain_config = chain_config
        self.markets = markets


class CLIContext(BaseModel):
    markets_config: List[PowerloomChainConfig]
    chain_markets_map: Dict[str, ChainMarketData]
    available_environments: Set[str]  # These are the valid chain names (UPPERCASE)
    available_markets: Set[str]

    class Config:
        arbitrary_types_allowed = True
