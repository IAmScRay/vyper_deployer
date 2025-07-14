# Vyper Deployer

This repo contains a compile-and-deploy program that takes smart contract code written in Vyper, compiles & deploys it to the network of your choice!

Features:
* it's simple & lightweight!
* it can search for constructor arguments & take inputs approprietly!
* it does safe type checking & data conversion: from Python data types to EVM-compatible ones with ease!
* it saves deployment data (contract address, Vyper version, constructor arguments - if any, ABI) to a `.json` file after successful deployment!
* all you need is Vyper installed, your code & network you want to deploy on!

## Installation & usage
✅ Tested on Python 3.9.11 (Vyper 0.37), 3.11.5 (Vyper 0.43) **!**

1. Clone the repo & change current directory: `git clone https://github.com/IAmScRay/vyper_deployer && cd vyper_deployer`
2. Create & activate new virtual environment: `python3 -m venv venv && source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Write your own smart contract code ☺️
5. Start deployer & follow the instructions: `python3 main.py`

Deployments were successful on several testnets, including **Ethereum Holesky**, **Vana Satori** & **Citrea Devnet** but you are welcome to try other networks, too! ⭐️

First successful mainnet deployment was on Hemi Mainnet when deploying a ERC20 token `Maxcoin`: [explorer link](https://explorer.hemi.xyz/address/0xc8fc18299043e0C2D36C630fcD933db0c6f17042)
