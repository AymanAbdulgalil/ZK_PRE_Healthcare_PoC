const fs = require("fs");
const path = require("path");
const hre = require("hardhat");

// Hardhat's public dev accounts, never for a real chain: #0 deploys, owner and
// provider are #2 and #3. No constructor args: no account has special authority (R6).

async function main() {
  const [deployer] = await hre.ethers.getSigners();

  const AccessControl = await hre.ethers.getContractFactory("AccessControl", deployer);
  const contract = await AccessControl.deploy();
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  const artifact = await hre.artifacts.readArtifact("AccessControl");
  const network = await hre.ethers.provider.getNetwork();

  const outDir = path.join(__dirname, "..", "deployments");
  fs.mkdirSync(outDir, { recursive: true });

  const deployment = {
    contractName: "AccessControl",
    address,
    abi: artifact.abi,
    chainId: Number(network.chainId),
    rpcUrl: "http://ledger:8545",   // service DNS name inside net-ledger
    deployer: deployer.address,
    deployedAt: new Date().toISOString()
  };

  fs.writeFileSync(
    path.join(outDir, "AccessControl.json"),
    JSON.stringify(deployment, null, 2)
  );

  console.log(`AccessControl deployed to ${address}`);
  console.log(`Deployment info written to deployments/AccessControl.json`);
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
