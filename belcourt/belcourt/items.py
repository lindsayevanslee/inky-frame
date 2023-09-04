# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class BelcourtItem(scrapy.Item):
    # define the fields for your item here like:
    # name = scrapy.Field()
    currenttime = scrapy.Field()
    date = scrapy.Field()
    shows = scrapy.Field()
    #showtimes = scrapy.Field()
