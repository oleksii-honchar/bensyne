 
module.exports = {
  estimateTokenCount: jest.fn(str => Math.ceil(str.length / 4)),
  isWithinTokenLimit: jest.fn(() => true),
  sliceByTokens: jest.fn((str, maxTokens) => {
    const maxChars = maxTokens * 4;
    return str.length > maxChars ? str.slice(0, maxChars) : str;
  }),
  splitByTokens: jest.fn((str, maxTokens) => {
    const maxChars = maxTokens * 4;
    const chunks = [];
    for (let i = 0; i < str.length; i += maxChars) {
      chunks.push(str.slice(i, i + maxChars));
    }
    return chunks;
  }),
  approximateTokenSize: jest.fn(str => Math.ceil(str.length / 4)),
};
