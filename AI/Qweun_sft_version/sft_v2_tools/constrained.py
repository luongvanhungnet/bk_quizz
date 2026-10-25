"""LM Format Enforcer 0.11.3 adapter, also testable without torch.

Tokenizer preparation follows the package's documented Transformers integration;
only generation uses GPU tensors. Reuse prepared data for every sample.
"""
from functools import partial


def tokenizer_data(tokenizer):
    from lmformatenforcer import TokenEnforcerTokenizerData
    zero = tokenizer.encode("0", add_special_tokens=False)[-1]
    special = set(tokenizer.all_special_ids)
    regular = []
    for identity in range(len(tokenizer)):
        if identity in special: continue
        decoded = tokenizer.decode([zero, identity])[1:]
        original = tokenizer.decode([identity])
        regular.append((identity, decoded, len(decoded) > len(original)))
    return TokenEnforcerTokenizerData(regular, lambda ids: tokenizer.decode(ids).rstrip("�"),
                                     tokenizer.eos_token_id, False, len(tokenizer))


class Prefix:
    def __init__(self, data, schema):
        from lmformatenforcer import JsonSchemaParser, TokenEnforcer
        self.enforcer = TokenEnforcer(data, JsonSchemaParser(schema))

    def __call__(self, batch_id, sent):
        return self.enforcer.get_allowed_tokens(sent.tolist()).allowed_tokens


def batched_prefix(data, schemas):
    parsers = [Prefix(data, schema) for schema in schemas]
    return lambda batch_id, sent: parsers[batch_id](batch_id, sent)
