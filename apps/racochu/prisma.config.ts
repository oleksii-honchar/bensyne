import { defineConfig } from "@prisma/config";

export default defineConfig({
  datasource: {
    url: "file:./data/racochu.db",
  },
});
