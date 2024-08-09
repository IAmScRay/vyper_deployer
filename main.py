import binascii
import getpass
import json
import os
import re
import requests
import subprocess
import time

from eth_abi import encode
from eth_account.account import LocalAccount
from eth_utils import ValidationError
from hexbytes import HexBytes
from web3 import HTTPProvider, Web3


def get_vyper_init(filename) -> list:
    """
    Search & parse the constructor arguments in __init__ method of a smart contract.
    
    :param filename: .vy-filename
    :return: :class:`list` of arguments
    """
    with open(filename, "r") as file:
        vyper_code = file.read()

    pattern = re.compile(r"def\s+__init__\s*\(([^)]*)\)")
    match = pattern.search(vyper_code)

    if match:
        args = match.group(1).split(",")
        args = [arg.strip() for arg in args]
        if "" in args:
            return []
            
        return args
    else:
        return []


def get_size(arg_type) -> int:
    """
    Get the size from a given type.
    
    :param arg_type: argument's type like ``Bytes[100]`` or ``String[10]``
    :return: :class:`int` – size of a type (100 or 10 for the examples above),
    or ``-1`` (that's impossible but still 🙃)
    """
    pattern = r"\[(\d+)\]"

    match = re.search(pattern, arg_type)

    if match:
        return int(match.group(1))
    else:
        return -1


def get_chain_data(chain_id: int) -> dict:
    result = {
        "name": "Unknown",
        "ticker": "UNKWN",
        "explorer": ""
    }

    req = requests.get("https://chainid.network/chains.json")
    resp = req.json()

    for network_data in resp:
        if network_data["chainId"] == chain_id:
            result["name"] = network_data["name"]
            result["ticker"] = network_data["nativeCurrency"]["symbol"]
            result["explorer"] = network_data["explorers"][0]["url"] if len(network_data["explorers"]) > 0 else ""
            break
    
    return result


def convert(
    arg_type,
    value
) -> tuple:
    """
    Convert a given value and its Vyper type
    to an ABI-compatible type & value.
    
    :param arg_type: argument's type.
    :param value: entered value.
    :return: `class`:tuple` – a tuple with ``result[0]`` = ``ABI-compatible type``,
    ``result[1]`` = ``ABI-compatible value``, or an empty one if entered value is incorrect.
    """
    if arg_type == "address":
        try:
            return arg_type, Web3.to_checksum_address(value)
        except ValueError:
            return ()
    
    if arg_type.startswith("int"):
        size = int(arg_type[3::])
        if size < 8 or size > 256:
            return ()
        
        try:
            value = int(value)
        except ValueError:
            return ()
        
        return arg_type, value if -2 ** (size - 1) <= value <= 2 ** (size - 1) - 1 else ()
    
    if arg_type.startswith("uint"):
        size = int(arg_type[4::])
        if size < 8 or size > 256:
            return ()
        
        try:
            value = int(value)
        except ValueError:
            return ()
        
        return arg_type, value if 0 <= value <= (2 ** size - 1) else ()
    
    if arg_type.startswith("bytes"):
        size = int(arg_type[5::])
        try:
            value = HexBytes(value)
        except binascii.Error:
            return ()
        
        return arg_type, value if len(value) <= size else ()
    
    if arg_type.startswith("Bytes"):
        size = get_size(arg_type)
        try:
            value = HexBytes(value)
        except binascii.Error:
            value = "0x" + bytes(value, encoding="utf-8").hex()
            return "bytes", value if len(value) <= size else ()
        
        return "bytes", value if len(value) <= size else ()
    
    if arg_type.startswith("String"):
        size = get_size(arg_type)
        try:
            value = str(value)
        except ValueError:
            return ()
        
        return "string", value if len(value) <= size else ()


def deploy(
    filename: str,
    bytecode: str,
    abi: str,
    vyper_version: str,
    constructor_args: str = "",
):
    """
    Retrieve deployer wallet's private key / mnemonic phrase, create
    deploy transaction, if it's a success – save an ABI to a ``.json``.

    :param filename: contract's filename
    :param bytecode: compiled bytecode
    :param abi: contract's ABI
    :param vyper_version: compiler version
    :param constructor_args: hex-encoded constructor arguments (if any)
    """

    provider = None
    chain_data = {}
    while provider is None:
        p_url = input("🔗 Enter URL for the network's RPC of your choice: ")
        if not p_url.startswith("http://") and not p_url.startswith("https://"):
            print("🤨 Incorrect URL! Make sure it starts with `http://` or `https://` & try again.\n")
            continue
        
        p = Web3(HTTPProvider(p_url))
        if not p.is_connected():
            print("😢 Cannot connect to specified RPC! Get a different URL & try again.\n")
            continue
        
        chain_id = p.eth.chain_id
        chain_data = get_chain_data(chain_id)
        
        if chain_data["name"] == "Unknown":
            proceed = input("🤔 Seems like it's an unknown network for the world! Are you sure you want to continue? (y/N)")
            if proceed.lower() != "y":
                print("🚫 Make sure to use correct URL & try again.\n")
                continue
        
        provider = p
    
    print(f"🌈 Connected to {chain_data['name']}!\n")
    
    Web3().eth.account.enable_unaudited_hdwallet_features()
    
    account: LocalAccount = None
    while account is None:
        entry = getpass.getpass("🙈 Enter your deployer wallet's private key / mnemonic: ")
        if len(entry) == 64 or len(entry) == 66:  # private key
            account: LocalAccount = provider.eth.account.from_key(entry)
        else:  # seems like it's a mnemonic phrase
            try:
                account: LocalAccount = provider.eth.account.from_mnemonic(entry)
            except ValidationError:
                print("😓 Incorrect mnemonic phrase! Make sure you entered the correct one & try again.\n")
                continue
    
    print(f"🛂 Deployer's address: {account.address}")
    
    native_balance = provider.eth.get_balance(account.address, "latest")
    formatted_balance = round(
        provider.from_wei(native_balance, "ether"),
        ndigits=8
    )
    print(f"💰 Balance: {formatted_balance} {chain_data['ticker']}\n")
    
    deployment_fee = 3000000 * (provider.eth.gas_price // 100 * 150)
    formatted_fee = round(
        provider.from_wei(deployment_fee, "ether"),
        ndigits=8
    )
    
    if native_balance < deployment_fee:
        print(f"🚫 You do not have enough {chain_data['ticker']} in your wallet.")
        print(f"It's better to have at least {formatted_fee} {chain_data['ticker']} for a successful deployment.")
        exit(-1)
    
    print("🛠 Creating deployment transaction...")
    
    tx_data = {
        "chainId": provider.eth.chain_id,
        "from": account.address,
        "nonce": provider.eth.get_transaction_count(account.address, "latest"),
        "value": 0,
        "data": bytecode + constructor_args if constructor_args != "" else bytecode,
        "gas": 3000000,
        "gasPrice": provider.eth.gas_price // 100 * 150
    }
    
    signed = account.sign_transaction(tx_data)
    
    sent_tx = provider.eth.send_raw_transaction(signed.rawTransaction)
    print("✈️ Transaction sent!")
    print(f"TX hash: {sent_tx.hex()}\n")
    
    receipt = provider.eth.wait_for_transaction_receipt(
        sent_tx,
        poll_latency=0.25,
        timeout=180
    )
    
    if receipt["status"] == 1:
        print("🤩 Transaction successful!")
        print(f"⭐️ Deployed contract address: {receipt.contractAddress}")
        if chain_data["explorer"] != "":
            print(f"🌐 URL: {chain_data['explorer']}/address/{receipt.contractAddress}\n")
        else:
            print("🕸 Unfortunately, we couldn't find an explorer URL for you to see your contract – make sure to find one if you want to verify your contract!\n")
        
        json_filename = filename.split(".")[0]
        print(f"📝 Saving ABI file to `{json_filename}.json`...")

        try:
            os.mkdir(os.getcwd() + os.sep + "abi_files")
        except FileExistsError:
            pass

        if os.path.exists(os.getcwd() + os.sep + "abi_files" + os.sep + f"{json_filename}.json"):
            print(f"🔍It seems like there is already a file named `{json_filename}.json`!")
        
            cur_time = int(time.time())
            print(f"ABI will be saved to a new file named `{json_filename}-{cur_time}.json`")
            
            input("💪 Press ENTER to continue.\n")
            
            json_filename = json_filename + f"-{cur_time}"
            
        with open(os.getcwd() + os.sep + "abi_files" + os.sep + f"{json_filename}.json", "x") as abi_file:
            json.dump(json.loads(abi), abi_file, sort_keys=False, indent=2)
        
        print(f"👌 Saved ABI to abi_files/{json_filename}.json.")
        print(f"Make sure to select Vyper v{vyper_version} when verifying contract's code & "
              f"use generated ABI file when interacting with contract's functions.\n")
    else:
        print("😓 There was an execution error while deploying your contract. Sorry 😢")
        exit(-1)


def main():
    print("-" * 48)
    print("Vyper contract deployer")
    print("Author: @i_am_scray (https://github.com/IAmScRay")
    print("-" * 48, "\n")

    vy_filename = ""
    while vy_filename == "":
        f = input("📝 Enter Vyper contract filename (WITHOUT .vy extension): ")
        
        filename = f"{f}.vy"
        if not os.path.exists(filename):
            print(f"🧐 `{filename}` not found! Try again.\n")
            continue
        
        vy_filename = filename
    
    vyper_version_result = subprocess.run(["vyper", "--version"], capture_output=True, text=True)
    vyper_version = vyper_version_result.stdout.strip("\n")
    
    print(f"🛠 Compiling `{vy_filename}` using Vyper v{vyper_version}, please wait...\n")
    
    result = subprocess.run(["vyper", "-f", "bytecode,abi", vy_filename], capture_output=True, text=True)
    
    if not result.stdout.startswith("0x"):
        print("🤕 Compilation failed!")
        print("Output:\n", result.stderr)
        exit(-1)
        
    bytecode, text_abi = result.stdout.strip("\n").split("\n")
    
    print(f"✅ Compiled successfully!")
    print(f"🔍 Searching constructor & its arguments...")
    
    args = get_vyper_init(vy_filename)
    if len(args) == 0:
        print(f"😕 Looks like there is no constructor!")
        
        proceed = input("❓ Would you like to proceed with deployment? (y/n) ")
        if proceed.lower() == "y":
            deploy(
                filename=vy_filename,
                bytecode=bytecode,
                abi=text_abi,
                vyper_version=vyper_version
            )
        else:
            print("❌ Deployment cancelled.")
            exit(0)
    else:
        print(f"✨ Found {len(args)}", "argument!" if len(args) == 1 else "arguments!")
        
        types = []
        values = []
        for arg in args:
            name, arg_type = arg.replace(" ", "").split(":")
            
            value = ()
            while len(value) != 2:
                entry = input(f"📝 Write a value for argument `{name}`: ")
                if entry == "":
                    print("🚨 Value cannot be empty! Try again.\n")
                    continue
                
                value = convert(arg_type, entry)
                if len(value) == 2:
                    types.append(value[0])
                    values.append(value[1])
                    print("🤝 Saved successfully!\n")
                else:
                    print("❓ Incorrect value! Try again.\n")
                    continue

        encoded_args = encode(
            types,
            values
        ).hex()
        
        deploy(
            filename=vy_filename,
            bytecode=bytecode,
            abi=text_abi,
            vyper_version=vyper_version,
            constructor_args=encoded_args
        )
    
    print("\n🎆 Congratulations of your deployment!")
    print("Feedback is very appreacited! Made this with ♥️")
    

if __name__ == "__main__":
    main()
