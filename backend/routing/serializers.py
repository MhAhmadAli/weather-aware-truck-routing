from rest_framework import serializers


class PlanRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(max_length=200)
    destination = serializers.CharField(max_length=200)
    departure = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=1, max_value=200_000)
    interval_mi = serializers.ChoiceField(choices=[10, 25, 50], default=25)
