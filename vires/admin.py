#-------------------------------------------------------------------------------
#
# Project: EOxServer <http://eoxserver.org>
# Authors: Fabian Schindler <fabian.schindler@eox.at>
#
#-------------------------------------------------------------------------------
# Copyright (C) 2014 EOX IT Services GmbH
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies of this Software or works derived from this Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#-------------------------------------------------------------------------------

from django.contrib.gis import forms
from django.contrib.gis import admin
from eoxserver.resources.coverages.admin import CoverageAdmin, CollectionAdmin

from vires import models


class ProductAdmin(CoverageAdmin):
    fieldsets = (
        (None, {
            'fields': ('identifier', )
        }),
        ('Metadata', {
            'fields': ('range_type',
                       ('size_x', 'size_y'),
                       ('begin_time', 'end_time'),
                       'footprint',
                       'ground_path'),
            'description': 'Geospatial metadata'
        }),
    )

admin.site.register(models.Product, ProductAdmin)


#class ProductCollectionForm(forms.ModelForm):
#    def clean_srid(self)


class ProductCollectionAdmin(CollectionAdmin):
    model = models.ProductCollection
    #form  = ProductCollectionForm

    fieldsets = (
        (None, {
            'fields': ('identifier',)
        }),
        ('Metadata', {
            'fields': (('begin_time', 'end_time'), 'footprint', "ground_path")
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super(ProductCollectionAdmin, self).get_form(request, obj, **kwargs)
        base_fields = form.base_fields
        #form.base_fields['srid'].initial = 4326
        #form.base_fields['srid'].widget = forms.HiddenInput()

        return form

    def save_model(self, request, obj, form, change):
        print request, obj, form, change
        if not change:
            obj.extent = (-180, -90, 180, 90)
            obj.srid = 4326
            obj.ground_path = None
        obj.save()

    #inlines = (DataSourceInline, EOObjectInline, CollectionInline)

admin.site.register(models.ProductCollection, ProductCollectionAdmin)
