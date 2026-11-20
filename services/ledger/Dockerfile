# IMAGE: ledger  (Node/Hardhat -- local chain + AccessControl.sol deployment)
#
FROM node:20-alpine

RUN apk add --no-cache curl

WORKDIR /app

# Install deps first for better layer caching
COPY package.json ./
RUN npm install

COPY hardhat.config.js ./
COPY contracts ./contracts
COPY scripts ./scripts
COPY test ./test
COPY entrypoint.sh ./

RUN chmod +x entrypoint.sh \
    && npx hardhat compile

# Contract tests: docker compose exec ledger npx hardhat test

# Mount point of the `ledger-data` volume; the deployment JSON is written here.
RUN mkdir -p /app/deployments \
    && addgroup -S ledger \
    && adduser -S ledger -G ledger \
    && chown -R ledger:ledger /app

USER ledger

EXPOSE 8545

ENTRYPOINT ["./entrypoint.sh"]