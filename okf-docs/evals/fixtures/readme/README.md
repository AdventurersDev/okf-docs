# 🚀 Ledgerline

## ✨ Welcome to Ledgerline!

In today's fast-paced world, managing your personal finances can feel overwhelming. That's where **Ledgerline** comes in! Ledgerline is a **powerful**, **robust** and **seamless** command-line tool that lets you **unlock** the full potential of your bank data. It's not just an importer, it's a complete ledger for your money.

It is important to note that Ledgerline basically leverages cutting-edge parsing to turn your bank's CSV exports into clean, categorized transactions.

## 📦 Installation

Getting started is super easy! Ledgerline generally requires Node.js 20 or later. Simply run the following command and you'll be up and running in no time:

```
npm install -g ledgerline
```

## 🛠️ Usage

Using Ledgerline is a breeze. To import a bank export, you might potentially want to run:

```
ledgerline import statement.csv
```

By default, amounts are read as euros. If your bank uses a different currency, feel free to pass the `--currency` flag, for example `--currency USD`. The default is `EUR`.

## ⚙️ Configuration

Ledgerline reads its settings from `~/.ledgerline.toml`. To sync with the Ledgerline cloud, you'll need to set the `LEDGERLINE_TOKEN` environment variable. Without it, sync is basically disabled.

## ⚠️ Limitations

Ledgerline is incredibly fast, but please note that files over 50 MB are rejected with the error `FILE_TOO_LARGE`. We're working hard to make this even better!

## 🙌 Conclusion

In summary, Ledgerline is the ultimate tool for importing bank exports, with easy installation, flexible currency support and seamless cloud sync. We hope you enjoy using it as much as we enjoyed building it! Happy budgeting! 🎉

## 📄 License

Ledgerline is released under the MIT License.
