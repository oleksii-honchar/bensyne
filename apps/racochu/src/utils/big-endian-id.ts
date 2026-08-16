/**
 * Big-endian sortable ID generator (Snowflake-style).
 * Adapted from voqaria's typescript-common/big-endian-id.
 *
 * Layout: 41 bits timestamp (ms since epoch) + 10 bits node + 12 bits sequence.
 * The result IS a 64-bit unsigned integer (BigInt), stored natively as a 64-bit
 * integer in the database. No string conversion.
 */

const EPOCH = 1577836800000n; // 2020-01-01
const NODE_BITS = 10n;
const SEQ_BITS = 12n;
const MAX_NODE = (1n << NODE_BITS) - 1n;
const MAX_SEQ = (1n << SEQ_BITS) - 1n;
const NODE_SHIFT = SEQ_BITS;
const TIME_SHIFT = SEQ_BITS + NODE_BITS;

let lastTimestamp = 0n;
let sequence = 0n;

const NODE_ID = 1;
const node = BigInt(NODE_ID);

if (NODE_ID < 0 || NODE_ID > Number(MAX_NODE)) {
  throw new Error(`Invalid nodeId ${NODE_ID}. Must be between 0 and ${MAX_NODE.toString()}`);
}

function generate(): bigint {
  let now = BigInt(Date.now());

  if (now === lastTimestamp) {
    sequence = (sequence + 1n) & MAX_SEQ;
    if (sequence === 0n) {
      while (now === lastTimestamp) {
        now = BigInt(Date.now());
      }
    }
  } else {
    sequence = 0n;
  }

  lastTimestamp = now;

  const timePart = (now - EPOCH) << TIME_SHIFT;
  const nodePart = node << NODE_SHIFT;

  return timePart | nodePart | sequence;
}

/**
 * Generates a new big-endian ID as a 64-bit integer (BigInt).
 */
export function generateId(): bigint {
  return generate();
}
