"""Runtime decoder for Upstox Market Data Feed V3 protobuf messages."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.json_format import MessageToDict


def _field(msg, name: str, number: int, field_type: int, *, label: int = 1, type_name: str = "") -> None:
    f = msg.field.add()
    f.name = name
    f.number = number
    f.label = label
    f.type = field_type
    if type_name:
        f.type_name = type_name


def _message(file_proto, name: str):
    msg = file_proto.message_type.add()
    msg.name = name
    return msg


def _enum(file_proto, name: str, values: list[tuple[str, int]]) -> None:
    enum = file_proto.enum_type.add()
    enum.name = name
    for item_name, item_number in values:
        value = enum.value.add()
        value.name = item_name
        value.number = item_number


@lru_cache(maxsize=1)
def _feed_response_cls():
    package = "com.upstox.marketdatafeederv3udapi.rpc.proto"
    file_proto = descriptor_pb2.FileDescriptorProto()
    file_proto.name = "MarketDataFeedV3.proto"
    file_proto.package = package
    file_proto.syntax = "proto3"

    _enum(file_proto, "Type", [("initial_feed", 0), ("live_feed", 1), ("market_info", 2)])
    _enum(file_proto, "RequestMode", [("ltpc", 0), ("full_d5", 1), ("option_greeks", 2), ("full_d30", 3)])
    _enum(
        file_proto,
        "MarketStatus",
        [
            ("PRE_OPEN_START", 0),
            ("PRE_OPEN_END", 1),
            ("NORMAL_OPEN", 2),
            ("NORMAL_CLOSE", 3),
            ("CLOSING_START", 4),
            ("CLOSING_END", 5),
        ],
    )

    ltpc = _message(file_proto, "LTPC")
    _field(ltpc, "ltp", 1, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)
    _field(ltpc, "ltt", 2, descriptor_pb2.FieldDescriptorProto.TYPE_INT64)
    _field(ltpc, "ltq", 3, descriptor_pb2.FieldDescriptorProto.TYPE_INT64)
    _field(ltpc, "cp", 4, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)

    quote = _message(file_proto, "Quote")
    _field(quote, "bidQ", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT64)
    _field(quote, "bidP", 2, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)
    _field(quote, "askQ", 3, descriptor_pb2.FieldDescriptorProto.TYPE_INT64)
    _field(quote, "askP", 4, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)

    market_level = _message(file_proto, "MarketLevel")
    _field(
        market_level,
        "bidAskQuote",
        1,
        descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
        label=descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
        type_name=f".{package}.Quote",
    )

    ohlc = _message(file_proto, "OHLC")
    _field(ohlc, "interval", 1, descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
    _field(ohlc, "open", 2, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)
    _field(ohlc, "high", 3, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)
    _field(ohlc, "low", 4, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)
    _field(ohlc, "close", 5, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)
    _field(ohlc, "vol", 6, descriptor_pb2.FieldDescriptorProto.TYPE_INT64)
    _field(ohlc, "ts", 7, descriptor_pb2.FieldDescriptorProto.TYPE_INT64)

    market_ohlc = _message(file_proto, "MarketOHLC")
    _field(
        market_ohlc,
        "ohlc",
        1,
        descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
        label=descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
        type_name=f".{package}.OHLC",
    )

    greeks = _message(file_proto, "OptionGreeks")
    for idx, name in enumerate(("delta", "theta", "gamma", "vega", "rho"), start=1):
        _field(greeks, name, idx, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)

    market_full = _message(file_proto, "MarketFullFeed")
    _field(market_full, "ltpc", 1, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.LTPC")
    _field(market_full, "marketLevel", 2, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.MarketLevel")
    _field(market_full, "optionGreeks", 3, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.OptionGreeks")
    _field(market_full, "marketOHLC", 4, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.MarketOHLC")
    _field(market_full, "atp", 5, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)
    _field(market_full, "vtt", 6, descriptor_pb2.FieldDescriptorProto.TYPE_INT64)
    _field(market_full, "oi", 7, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)
    _field(market_full, "iv", 8, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)
    _field(market_full, "tbq", 9, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)
    _field(market_full, "tsq", 10, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)

    index_full = _message(file_proto, "IndexFullFeed")
    _field(index_full, "ltpc", 1, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.LTPC")
    _field(index_full, "marketOHLC", 2, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.MarketOHLC")

    full_feed = _message(file_proto, "FullFeed")
    oneof = full_feed.oneof_decl.add()
    oneof.name = "FullFeedUnion"
    _field(full_feed, "marketFF", 1, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.MarketFullFeed")
    full_feed.field[-1].oneof_index = 0
    _field(full_feed, "indexFF", 2, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.IndexFullFeed")
    full_feed.field[-1].oneof_index = 0

    first_level = _message(file_proto, "FirstLevelWithGreeks")
    _field(first_level, "ltpc", 1, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.LTPC")
    _field(first_level, "firstDepth", 2, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.Quote")
    _field(first_level, "optionGreeks", 3, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.OptionGreeks")
    _field(first_level, "vtt", 4, descriptor_pb2.FieldDescriptorProto.TYPE_INT64)
    _field(first_level, "oi", 5, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)
    _field(first_level, "iv", 6, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)

    feed = _message(file_proto, "Feed")
    feed_oneof = feed.oneof_decl.add()
    feed_oneof.name = "FeedUnion"
    _field(feed, "ltpc", 1, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.LTPC")
    feed.field[-1].oneof_index = 0
    _field(feed, "fullFeed", 2, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.FullFeed")
    feed.field[-1].oneof_index = 0
    _field(feed, "firstLevelWithGreeks", 3, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.FirstLevelWithGreeks")
    feed.field[-1].oneof_index = 0
    _field(feed, "requestMode", 4, descriptor_pb2.FieldDescriptorProto.TYPE_ENUM, type_name=f".{package}.RequestMode")

    market_info = _message(file_proto, "MarketInfo")
    seg_entry = market_info.nested_type.add()
    seg_entry.name = "SegmentStatusEntry"
    seg_entry.options.map_entry = True
    _field(seg_entry, "key", 1, descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
    _field(seg_entry, "value", 2, descriptor_pb2.FieldDescriptorProto.TYPE_ENUM, type_name=f".{package}.MarketStatus")
    _field(
        market_info,
        "segmentStatus",
        1,
        descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
        label=descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
        type_name=f".{package}.MarketInfo.SegmentStatusEntry",
    )

    response = _message(file_proto, "FeedResponse")
    feeds_entry = response.nested_type.add()
    feeds_entry.name = "FeedsEntry"
    feeds_entry.options.map_entry = True
    _field(feeds_entry, "key", 1, descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
    _field(feeds_entry, "value", 2, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.Feed")
    _field(response, "type", 1, descriptor_pb2.FieldDescriptorProto.TYPE_ENUM, type_name=f".{package}.Type")
    _field(
        response,
        "feeds",
        2,
        descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
        label=descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
        type_name=f".{package}.FeedResponse.FeedsEntry",
    )
    _field(response, "currentTs", 3, descriptor_pb2.FieldDescriptorProto.TYPE_INT64)
    _field(response, "marketInfo", 4, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name=f".{package}.MarketInfo")

    pool = descriptor_pool.DescriptorPool()
    pool.Add(file_proto)
    desc = pool.FindMessageTypeByName(f"{package}.FeedResponse")
    return message_factory.GetMessageClass(desc)


def decode_feed_response(raw: bytes) -> dict[str, Any]:
    msg = _feed_response_cls()()
    msg.ParseFromString(raw)
    return MessageToDict(
        msg,
        preserving_proto_field_name=True,
        use_integers_for_enums=False,
    )
